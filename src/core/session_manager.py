"""Session Manager - Session lifecycle and message storage."""

from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import select, func, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Session, SessionStatus, Message, Project
from src.core.exceptions import (
    SessionNotFoundError,
    SessionStateError,
    ProjectNotFoundError,
)
from src.core.constants import LAST_PROMPT_MAX_LENGTH, DEFAULT_LIST_LIMIT, DEFAULT_LIST_OFFSET
from src.core.types import PendingApproval


# Valid state transitions based on the state machine diagram
# From state -> set of valid target states
VALID_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.IDLE: {SessionStatus.RUNNING},
    SessionStatus.RUNNING: {
        SessionStatus.WAITING_APPROVAL,
        SessionStatus.COMPLETED,
        SessionStatus.ERROR,
    },
    SessionStatus.WAITING_APPROVAL: {SessionStatus.RUNNING},
    SessionStatus.COMPLETED: {SessionStatus.RUNNING},  # Can resume from completed
    SessionStatus.ERROR: {SessionStatus.RUNNING},  # Can retry from error
}


class SessionManager:
    """Manages session lifecycle, message storage, and state transitions.

    Responsibilities:
    - Create session records with unique IDs
    - Store message history with full metadata
    - Track session status with valid state transitions
    - Map our session IDs to Claude's session IDs
    - Handle pending approval state

    State Machine:
        IDLE -> RUNNING (start_session)
        RUNNING -> WAITING_APPROVAL (tool requires approval)
        RUNNING -> COMPLETED (agent completes)
        RUNNING -> ERROR (error occurs)
        WAITING_APPROVAL -> RUNNING (approve/deny)
        ERROR -> RUNNING (retry)
    """

    def __init__(self, db: AsyncSession):
        """Initialize with database session.

        Args:
            db: Async SQLAlchemy session
        """
        self.db = db

    async def create_session(
        self,
        project_id: str,
        name: str | None = None,
        initial_prompt: str | None = None,
        claude_session_id: str | None = None,
    ) -> Session:
        """Create a new session for a project.

        Args:
            project_id: The project's UUID
            name: Optional display name for the session
            initial_prompt: Optional initial prompt text
            claude_session_id: Optional pre-existing Claude session ID (for continuing external sessions)

        Returns:
            The created Session in IDLE status

        Raises:
            ProjectNotFoundError: If project doesn't exist
        """
        # Verify project exists
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        if not result.scalar_one_or_none():
            raise ProjectNotFoundError(f"Project not found: {project_id}")

        session = Session(
            project_id=project_id,
            name=name,
            status=SessionStatus.IDLE.value,
            last_prompt=initial_prompt,
            claude_session_id=claude_session_id,
            message_count=0,
            total_cost_usd=0.0,
        )

        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        return session

    async def get_session(
        self,
        session_id: str,
        include_messages: bool = False,
    ) -> Session:
        """Get a session by ID.

        Args:
            session_id: The session's UUID
            include_messages: Whether to eager load messages

        Returns:
            The Session

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        query = select(Session).where(Session.id == session_id)

        if include_messages:
            query = query.options(selectinload(Session.messages))

        result = await self.db.execute(query)
        session = result.scalar_one_or_none()

        if not session:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        return session

    async def get_session_by_claude_id(self, claude_session_id: str) -> Session | None:
        """Get a session by Claude's session ID.

        Args:
            claude_session_id: Claude SDK's session ID

        Returns:
            The Session or None if not found
        """
        result = await self.db.execute(
            select(Session).where(Session.claude_session_id == claude_session_id)
        )
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        project_id: str | None = None,
        status: SessionStatus | None = None,
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = DEFAULT_LIST_OFFSET,
    ) -> Sequence[Session]:
        """List sessions with optional filters.

        Args:
            project_id: Filter by project (optional)
            status: Filter by status (optional)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of sessions, ordered by updated_at descending
        """
        query = select(Session).order_by(Session.updated_at.desc())

        if project_id:
            query = query.where(Session.project_id == project_id)
        if status:
            query = query.where(Session.status == status.value)

        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_session_status(
        self,
        session_id: str,
        new_status: SessionStatus,
        error_message: str | None = None,
        claude_session_id: str | None = None,
    ) -> Session:
        """Update a session's status with state machine validation.

        Args:
            session_id: The session's UUID
            new_status: The new status
            error_message: Error details if transitioning to ERROR
            claude_session_id: Claude's session ID (set on first RUNNING transition)

        Returns:
            The updated Session

        Raises:
            SessionNotFoundError: If session doesn't exist
            SessionStateError: If the transition is invalid
        """
        session = await self.get_session(session_id)
        current_status = session.status_enum

        # Validate state transition
        valid_targets = VALID_TRANSITIONS.get(current_status, set())
        if new_status not in valid_targets:
            raise SessionStateError(
                f"Invalid state transition: {current_status.value} -> {new_status.value}. "
                f"Valid transitions from {current_status.value}: {[s.value for s in valid_targets]}"
            )

        # Apply transition
        session.set_status(new_status)

        # Set error message if transitioning to ERROR
        if new_status == SessionStatus.ERROR:
            session.error_message = error_message
        elif new_status == SessionStatus.RUNNING:
            # Clear error when resuming from error
            session.error_message = None

        # Set Claude session ID if provided (usually on first RUNNING)
        if claude_session_id:
            session.claude_session_id = claude_session_id

        # Clear pending approval when moving away from WAITING_APPROVAL
        if current_status == SessionStatus.WAITING_APPROVAL:
            session.pending_approval = None

        await self.db.commit()
        await self.db.refresh(session)

        return session

    async def set_pending_approval(
        self,
        session_id: str,
        approval_data: PendingApproval,
    ) -> Session:
        """Set pending approval for a session and transition to WAITING_APPROVAL.

        Args:
            session_id: The session's UUID
            approval_data: Complete approval data dict (from ApprovalHandler.to_pending_approval)

        Returns:
            The updated Session

        Raises:
            SessionNotFoundError: If session doesn't exist
            SessionStateError: If not in RUNNING state
        """
        session = await self.get_session(session_id)

        if session.status_enum != SessionStatus.RUNNING:
            raise SessionStateError(
                f"Can only set pending approval from RUNNING state, "
                f"current state: {session.status}"
            )

        session.pending_approval = dict(approval_data)
        session.set_status(SessionStatus.WAITING_APPROVAL)

        await self.db.commit()
        await self.db.refresh(session)

        return session

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        message_type: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Message:
        """Add a message to a session.

        Args:
            session_id: The session's UUID
            role: Message role (user, assistant, system, tool_use, tool_result)
            content: Message content
            message_type: SDK message type for reconstruction
            extra: Additional metadata

        Returns:
            The created Message

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        # Verify session exists
        session = await self.get_session(session_id)

        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            message_type=message_type,
            extra=extra,
        )

        self.db.add(message)

        # Update session message count
        session.message_count += 1

        # Update last_prompt if this is a user message
        if role == "user":
            session.last_prompt = content[:LAST_PROMPT_MAX_LENGTH]

        await self.db.commit()
        await self.db.refresh(message)

        return message

    async def get_messages(
        self,
        session_id: str,
        limit: int | None = None,
        since: datetime | None = None,
    ) -> Sequence[Message]:
        """Get messages for a session.

        Args:
            session_id: The session's UUID
            limit: Maximum number of messages (optional)
            since: Only messages after this timestamp (optional)

        Returns:
            List of messages, ordered by timestamp

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        # Verify session exists
        await self.get_session(session_id)

        query = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.timestamp)
        )

        if since:
            query = query.where(Message.timestamp > since)
        if limit:
            query = query.limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_session_cost(
        self,
        session_id: str,
        cost_usd: float,
    ) -> Session:
        """Update the cumulative cost for a session.

        Args:
            session_id: The session's UUID
            cost_usd: Cost to add (not total, will be added to existing)

        Returns:
            The updated Session

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        session = await self.get_session(session_id)
        session.total_cost_usd += cost_usd

        await self.db.commit()
        await self.db.refresh(session)

        return session

    async def complete_session(
        self,
        session_id: str,
        final_cost_usd: float | None = None,
    ) -> Session:
        """Mark a session as completed.

        Args:
            session_id: The session's UUID
            final_cost_usd: Final total cost (optional, adds to existing)

        Returns:
            The updated Session

        Raises:
            SessionNotFoundError: If session doesn't exist
            SessionStateError: If not in RUNNING state
        """
        if final_cost_usd:
            await self.update_session_cost(session_id, final_cost_usd)

        return await self.update_session_status(session_id, SessionStatus.COMPLETED)

    async def fail_session(
        self,
        session_id: str,
        error_message: str,
    ) -> Session:
        """Mark a session as failed with an error.

        Args:
            session_id: The session's UUID
            error_message: Description of the error

        Returns:
            The updated Session

        Raises:
            SessionNotFoundError: If session doesn't exist
            SessionStateError: If not in RUNNING state
        """
        return await self.update_session_status(
            session_id,
            SessionStatus.ERROR,
            error_message=error_message,
        )

    async def list_sessions_with_count(
        self,
        project_id: str | None = None,
        status: SessionStatus | None = None,
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = DEFAULT_LIST_OFFSET,
    ) -> tuple[Sequence[Session], int]:
        """List sessions with optional filters and return total count.

        Args:
            project_id: Filter by project (optional)
            status: Filter by status (optional)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            Tuple of (sessions list, total count in database)
        """
        # Build base filter conditions
        conditions = []
        if project_id:
            conditions.append(Session.project_id == project_id)
        if status:
            conditions.append(Session.status == status.value)

        # Get total count
        count_query = select(func.count(Session.id))
        for cond in conditions:
            count_query = count_query.where(cond)
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Get paginated sessions
        query = select(Session).order_by(Session.updated_at.desc())
        for cond in conditions:
            query = query.where(cond)
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        sessions = result.scalars().all()

        return sessions, total

    async def get_messages_with_count(
        self,
        session_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[Sequence[Message], int]:
        """Get messages for a session with total count.

        Args:
            session_id: The session's UUID
            limit: Maximum number of messages (optional)
            offset: Number of messages to skip

        Returns:
            Tuple of (messages list, total count)

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        # Verify session exists
        await self.get_session(session_id)

        # Get total count
        count_query = select(func.count(Message.id)).where(
            Message.session_id == session_id
        )
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Get paginated messages
        query = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.timestamp)
            .offset(offset)
        )
        if limit:
            query = query.limit(limit)

        result = await self.db.execute(query)
        messages = result.scalars().all()

        return messages, total

    async def delete_session(self, session_id: str) -> None:
        """Delete a session and all its messages.

        Args:
            session_id: The session's UUID

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        session = await self.get_session(session_id)

        # Delete messages first (cascade should handle this, but explicit is better)
        await self.db.execute(
            sql_delete(Message).where(Message.session_id == session_id)
        )

        # Delete session
        await self.db.delete(session)
        await self.db.commit()
