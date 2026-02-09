"""Agent session orchestration service.

This service handles all background agent session operations, including:
- Starting new sessions
- Resuming completed sessions
- Sending follow-up prompts
- Processing message streams
- Managing tool approval workflow

All operations are designed to run as background tasks with their own
database sessions to avoid lifecycle issues.
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

from src.core.agent_runtime import AgentRuntime
from src.core.session_manager import SessionManager
from src.core.approval_handler import ApprovalHandler
from src.core.exceptions import (
    AgentSessionError,
    AgentConnectionError,
    SessionStateError,
)
from src.models import SessionStatus, Project
from src.services.message_mapper import MessageMapper
from src.api.deps import get_background_db_session

logger = logging.getLogger(__name__)


async def broadcast_approval_processed(
    session_id: str,
    approved: bool,
    feedback: str | None = None,
) -> None:
    """Broadcast an approval_processed message via WebSocket.

    This is a standalone function (not a method) because it doesn't
    require any orchestrator state — just the WebSocket manager.

    Args:
        session_id: The session ID
        approved: Whether the tool was approved
        feedback: User feedback if provided
    """
    try:
        from src.api.websocket.session_stream import get_connection_manager

        ws_manager = get_connection_manager()
        await ws_manager.broadcast(session_id, {
            "type": "approval_processed",
            "approved": approved,
            "feedback": feedback,
        })
    except Exception as e:
        logger.warning(f"Failed to broadcast approval_processed: {e}")


class AgentOrchestrator:
    """Orchestrates agent session lifecycle operations.

    This class encapsulates the complex logic for managing agent sessions,
    extracting it from the route handlers to improve testability and
    maintainability.

    All methods create their own database sessions to ensure proper
    lifecycle management in background tasks.
    """

    def __init__(
        self,
        runtime: AgentRuntime,
        approval_handler: ApprovalHandler | None = None,
    ):
        """Initialize the orchestrator.

        Args:
            runtime: The AgentRuntime instance for SDK operations
            approval_handler: Optional approval handler for tool approval workflow
        """
        self.runtime = runtime
        self.approval_handler = approval_handler
        self.mapper = MessageMapper()

    def _setup_approval_hooks(self, session_id: str) -> bool:
        """Set up approval hooks for a session if handler is available.

        Args:
            session_id: Our internal session ID

        Returns:
            True if hooks were enabled
        """
        if self.approval_handler is None:
            return False

        self.runtime.set_approval_handler(self.approval_handler)
        self.runtime.set_approval_callback(
            session_id,
            self._make_approval_callback(session_id),
        )
        return True

    async def start_session(
        self,
        project: Project,
        session_id: str,
        prompt: str,
    ) -> None:
        """Start a new agent session.

        This method:
        1. Transitions the session to RUNNING
        2. Sets up approval hooks if handler is available
        3. Streams messages from the agent
        4. Stores messages in the database
        5. Handles completion/error states

        Args:
            project: The project to run the session in
            session_id: Our internal session ID
            prompt: The initial prompt
        """
        enable_hooks = self._setup_approval_hooks(session_id)

        async for db in get_background_db_session():
            manager = SessionManager(db)

            try:
                await self._transition_to_running(manager, session_id)

                await self._process_message_stream(
                    stream=self.runtime.start_session(
                        project, prompt, session_id,
                        enable_approval_hooks=enable_hooks,
                    ),
                    manager=manager,
                    session_id=session_id,
                    capture_init=True,
                )

                # Ensure we end in a terminal state
                await self._ensure_terminal_state(manager, session_id)

            except (AgentSessionError, AgentConnectionError) as e:
                logger.error(f"Agent error for session {session_id}: {e}")
                await self._safe_fail_session(manager, session_id, str(e))

            except Exception as e:
                logger.exception(f"Unexpected error in session {session_id}")
                await self._safe_fail_session(
                    manager, session_id, f"Unexpected error: {e}"
                )

            finally:
                # Clean up: disconnect client so next prompt uses resume path
                await self.runtime.disconnect_session(session_id)
                if enable_hooks:
                    self.runtime.remove_approval_callback(session_id)

    async def resume_session(
        self,
        project: Project,
        session_id: str,
        claude_session_id: str,
        prompt: str,
    ) -> None:
        """Resume a completed session.

        Args:
            project: The project the session belongs to
            session_id: Our internal session ID
            claude_session_id: The Claude session ID for resumption
            prompt: The new prompt
        """
        enable_hooks = self._setup_approval_hooks(session_id)

        async for db in get_background_db_session():
            manager = SessionManager(db)

            try:
                # Transition to RUNNING (handles state machine properly)
                await self._transition_to_running(manager, session_id)

                # Store user message
                await manager.add_message(
                    session_id=session_id,
                    role="user",
                    content=prompt,
                    message_type="user",
                )

                await self._process_message_stream(
                    stream=self.runtime.resume_session(
                        project, prompt, session_id, claude_session_id,
                        enable_approval_hooks=enable_hooks,
                    ),
                    manager=manager,
                    session_id=session_id,
                    capture_init=False,
                )

                await self._ensure_terminal_state(manager, session_id)

            except Exception as e:
                logger.exception(f"Error resuming session {session_id}")
                await self._safe_fail_session(manager, session_id, str(e))

            finally:
                # Clean up: disconnect client so next prompt uses resume path
                await self.runtime.disconnect_session(session_id)
                if enable_hooks:
                    self.runtime.remove_approval_callback(session_id)

    async def _process_message_stream(
        self,
        stream: AsyncIterator[dict[str, Any]],
        manager: SessionManager,
        session_id: str,
        capture_init: bool = True,
    ) -> None:
        """Process a stream of messages from the agent.

        This is the core message processing loop, unified for all operations.

        Args:
            stream: Async iterator of messages from the runtime
            manager: Session manager for database operations
            session_id: The session ID
            capture_init: Whether to capture and store the Claude session ID
        """
        async for message in stream:
            msg_type = message.get("type", "")

            # Capture Claude session ID from init message
            if capture_init:
                claude_id = self.mapper.get_session_id_from_init(message)
                if claude_id:
                    # Session is already RUNNING — just store the Claude session ID
                    session = await manager.get_session(session_id)
                    session.claude_session_id = claude_id
                    await manager.db.commit()

            # Store message if it has storable content
            role = self.mapper.get_role(msg_type)
            content = self.mapper.get_content(message)

            if role and content:
                await manager.add_message(
                    session_id=session_id,
                    role=role,
                    content=content,
                    message_type=msg_type,
                    extra=message,
                )

            # Handle completion
            if self.mapper.is_completion_message(message):
                cost = self.mapper.get_cost(message)
                if cost:
                    await manager.update_session_cost(session_id, cost)

                if self.mapper.is_successful_completion(message):
                    await manager.complete_session(session_id)
                else:
                    error_msg = self.mapper.get_error_message(message)
                    await manager.fail_session(session_id, error_msg)

    def _make_approval_callback(self, session_id: str):
        """Create an approval callback for a session.

        The callback is invoked by the runtime's PreToolUse hook when
        a tool requires approval. It updates the session state in the
        database and broadcasts a WebSocket message.

        Args:
            session_id: Our session ID

        Returns:
            Async callback function
        """
        handler = self.approval_handler

        async def on_approval_required(
            sid: str,
            tool_name: str,
            tool_input: dict[str, Any],
            tool_use_id: str,
        ) -> None:
            """Handle approval required event."""
            async for db in get_background_db_session():
                manager = SessionManager(db)

                try:
                    request = await handler.get_pending(sid)
                    if not request:
                        return

                    approval_data = handler.to_pending_approval(request)

                    await manager.set_pending_approval(sid, approval_data)
                    await self._broadcast_approval_required(sid, approval_data)

                except Exception as e:
                    logger.exception(
                        f"Error handling approval for session {sid}: {e}"
                    )

        return on_approval_required

    async def _broadcast_approval_required(
        self,
        session_id: str,
        approval_data: dict[str, Any],
    ) -> None:
        """Broadcast an approval_required message via WebSocket.

        Args:
            session_id: The session ID
            approval_data: PendingApproval dict with all approval fields
        """
        try:
            from src.api.websocket.session_stream import get_connection_manager

            ws_manager = get_connection_manager()
            await ws_manager.broadcast(session_id, {
                "type": "approval_required",
                **approval_data,
            })
        except Exception as e:
            logger.warning(f"Failed to broadcast approval_required: {e}")

    async def _ensure_terminal_state(
        self,
        manager: SessionManager,
        session_id: str,
    ) -> None:
        """Ensure session is in a terminal state after stream ends.

        If we exit the message stream without receiving a result message,
        mark the session as completed.

        Args:
            manager: Session manager
            session_id: The session ID
        """
        session = await manager.get_session(session_id)
        if session.status_enum == SessionStatus.RUNNING:
            await manager.complete_session(session_id)

    async def _transition_to_running(
        self,
        manager: SessionManager,
        session_id: str,
    ) -> None:
        """Transition a session to RUNNING state.

        The state machine supports IDLE, COMPLETED, and ERROR → RUNNING.

        Args:
            manager: Session manager
            session_id: The session ID
        """
        session = await manager.get_session(session_id)
        if session.status_enum == SessionStatus.RUNNING:
            return
        await manager.update_session_status(session_id, SessionStatus.RUNNING)

    async def _safe_fail_session(
        self,
        manager: SessionManager,
        session_id: str,
        error_message: str,
    ) -> None:
        """Safely fail a session, handling already-terminal states.

        Args:
            manager: Session manager
            session_id: The session ID
            error_message: The error message to store
        """
        try:
            await manager.fail_session(session_id, error_message)
        except SessionStateError:
            # Already in a terminal state, ignore
            pass
