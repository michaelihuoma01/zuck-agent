"""Tests for SessionManager."""

import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import (
    SessionManager,
    SessionNotFoundError,
    SessionStateError,
    ProjectNotFoundError,
)
from src.models import Project, Session, SessionStatus, Message


@pytest.fixture
async def project(db_session: AsyncSession) -> Project:
    """Create a test project."""
    project = Project(
        name="Test Project",
        path="/test/project/path",
        permission_mode="default",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


class TestSessionManager:
    """Tests for the SessionManager class."""

    async def test_create_session(self, db_session: AsyncSession, project: Project):
        """Test creating a new session."""
        manager = SessionManager(db_session)

        session = await manager.create_session(
            project_id=project.id,
            name="My Session",
            initial_prompt="Hello!",
        )

        assert session.id is not None
        assert session.project_id == project.id
        assert session.name == "My Session"
        assert session.last_prompt == "Hello!"
        assert session.status == SessionStatus.IDLE.value
        assert session.message_count == 0
        assert session.total_cost_usd == 0.0

    async def test_create_session_project_not_found(self, db_session: AsyncSession):
        """Test creating session with nonexistent project raises error."""
        manager = SessionManager(db_session)

        with pytest.raises(ProjectNotFoundError, match="not found"):
            await manager.create_session(
                project_id="nonexistent-uuid",
                name="Orphan Session",
            )

    async def test_get_session(self, db_session: AsyncSession, project: Project):
        """Test getting a session by ID."""
        manager = SessionManager(db_session)

        created = await manager.create_session(
            project_id=project.id,
            name="Get Test",
        )

        fetched = await manager.get_session(created.id)

        assert fetched.id == created.id
        assert fetched.name == "Get Test"

    async def test_get_session_not_found(self, db_session: AsyncSession):
        """Test getting a nonexistent session raises error."""
        manager = SessionManager(db_session)

        with pytest.raises(SessionNotFoundError, match="not found"):
            await manager.get_session("nonexistent-uuid")

    async def test_get_session_with_messages(
        self, db_session: AsyncSession, project: Project
    ):
        """Test getting a session with messages included."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)
        await manager.update_session_status(session.id, SessionStatus.RUNNING)
        await manager.add_message(session.id, "user", "Hello!")

        fetched = await manager.get_session(session.id, include_messages=True)

        assert len(fetched.messages) == 1
        assert fetched.messages[0].content == "Hello!"

    async def test_get_session_by_claude_id(
        self, db_session: AsyncSession, project: Project
    ):
        """Test getting a session by Claude's session ID."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)
        await manager.update_session_status(
            session.id,
            SessionStatus.RUNNING,
            claude_session_id="claude-123-abc",
        )

        fetched = await manager.get_session_by_claude_id("claude-123-abc")

        assert fetched is not None
        assert fetched.id == session.id

    async def test_list_sessions(self, db_session: AsyncSession, project: Project):
        """Test listing sessions."""
        manager = SessionManager(db_session)

        for i in range(3):
            await manager.create_session(
                project_id=project.id,
                name=f"Session {i}",
            )

        sessions = await manager.list_sessions()

        assert len(sessions) == 3

    async def test_list_sessions_filter_by_project(
        self, db_session: AsyncSession, project: Project
    ):
        """Test listing sessions filtered by project."""
        manager = SessionManager(db_session)

        # Create another project
        other_project = Project(name="Other", path="/other/path")
        db_session.add(other_project)
        await db_session.commit()
        await db_session.refresh(other_project)

        # Create sessions in both projects
        await manager.create_session(project_id=project.id, name="P1 Session")
        await manager.create_session(project_id=other_project.id, name="P2 Session")

        sessions = await manager.list_sessions(project_id=project.id)

        assert len(sessions) == 1
        assert sessions[0].name == "P1 Session"

    async def test_list_sessions_filter_by_status(
        self, db_session: AsyncSession, project: Project
    ):
        """Test listing sessions filtered by status."""
        manager = SessionManager(db_session)

        s1 = await manager.create_session(project_id=project.id, name="Idle")
        s2 = await manager.create_session(project_id=project.id, name="Running")
        await manager.update_session_status(s2.id, SessionStatus.RUNNING)

        idle_sessions = await manager.list_sessions(status=SessionStatus.IDLE)
        running_sessions = await manager.list_sessions(status=SessionStatus.RUNNING)

        assert len(idle_sessions) == 1
        assert idle_sessions[0].name == "Idle"
        assert len(running_sessions) == 1
        assert running_sessions[0].name == "Running"

    # State Machine Tests

    async def test_state_idle_to_running(
        self, db_session: AsyncSession, project: Project
    ):
        """Test valid transition: IDLE -> RUNNING."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)
        assert session.status_enum == SessionStatus.IDLE

        updated = await manager.update_session_status(session.id, SessionStatus.RUNNING)

        assert updated.status_enum == SessionStatus.RUNNING

    async def test_state_running_to_completed(
        self, db_session: AsyncSession, project: Project
    ):
        """Test valid transition: RUNNING -> COMPLETED."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)
        await manager.update_session_status(session.id, SessionStatus.RUNNING)

        updated = await manager.complete_session(session.id, final_cost_usd=0.05)

        assert updated.status_enum == SessionStatus.COMPLETED
        assert updated.total_cost_usd == 0.05

    async def test_state_running_to_error(
        self, db_session: AsyncSession, project: Project
    ):
        """Test valid transition: RUNNING -> ERROR."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)
        await manager.update_session_status(session.id, SessionStatus.RUNNING)

        updated = await manager.fail_session(session.id, "Something went wrong")

        assert updated.status_enum == SessionStatus.ERROR
        assert updated.error_message == "Something went wrong"

    async def test_state_running_to_waiting_approval(
        self, db_session: AsyncSession, project: Project
    ):
        """Test valid transition: RUNNING -> WAITING_APPROVAL."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)
        await manager.update_session_status(session.id, SessionStatus.RUNNING)

        updated = await manager.set_pending_approval(
            session.id,
            {
                "tool_name": "Write",
                "tool_input": {"path": "test.py", "content": "print('hi')"},
                "tool_use_id": "toolu_123",
                "file_path": "test.py",
                "requested_at": "2026-02-06T00:00:00+00:00",
            },
        )

        assert updated.status_enum == SessionStatus.WAITING_APPROVAL
        assert updated.pending_approval["tool_name"] == "Write"
        assert updated.pending_approval["tool_use_id"] == "toolu_123"

    async def test_state_waiting_to_running(
        self, db_session: AsyncSession, project: Project
    ):
        """Test valid transition: WAITING_APPROVAL -> RUNNING (approve)."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)
        await manager.update_session_status(session.id, SessionStatus.RUNNING)
        await manager.set_pending_approval(
            session.id,
            {
                "tool_name": "Write",
                "tool_input": {},
                "tool_use_id": "toolu_123",
                "requested_at": "2026-02-06T00:00:00+00:00",
            },
        )

        # Simulate approval
        updated = await manager.update_session_status(session.id, SessionStatus.RUNNING)

        assert updated.status_enum == SessionStatus.RUNNING
        assert updated.pending_approval is None  # Cleared on transition

    async def test_state_error_to_running(
        self, db_session: AsyncSession, project: Project
    ):
        """Test valid transition: ERROR -> RUNNING (retry)."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)
        await manager.update_session_status(session.id, SessionStatus.RUNNING)
        await manager.fail_session(session.id, "Error!")

        updated = await manager.update_session_status(session.id, SessionStatus.RUNNING)

        assert updated.status_enum == SessionStatus.RUNNING
        assert updated.error_message is None  # Cleared on retry

    async def test_state_invalid_idle_to_completed(
        self, db_session: AsyncSession, project: Project
    ):
        """Test invalid transition: IDLE -> COMPLETED raises error."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)

        with pytest.raises(SessionStateError, match="Invalid state transition"):
            await manager.update_session_status(session.id, SessionStatus.COMPLETED)

    async def test_state_invalid_completed_to_anything(
        self, db_session: AsyncSession, project: Project
    ):
        """Test that COMPLETED is terminal state."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)
        await manager.update_session_status(session.id, SessionStatus.RUNNING)
        await manager.complete_session(session.id)

        # COMPLETED→RUNNING is valid (resume), but COMPLETED→ERROR is not
        with pytest.raises(SessionStateError, match="Invalid state transition"):
            await manager.update_session_status(session.id, SessionStatus.ERROR)

    # Message Tests

    async def test_add_message(self, db_session: AsyncSession, project: Project):
        """Test adding a message to a session."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)

        message = await manager.add_message(
            session.id,
            role="user",
            content="Hello, Claude!",
            message_type="user",
            extra={"tokens": 5},
        )

        assert message.id is not None
        assert message.role == "user"
        assert message.content == "Hello, Claude!"
        assert message.extra == {"tokens": 5}

        # Check session was updated
        updated_session = await manager.get_session(session.id)
        assert updated_session.message_count == 1
        assert updated_session.last_prompt == "Hello, Claude!"

    async def test_add_message_session_not_found(self, db_session: AsyncSession):
        """Test adding message to nonexistent session raises error."""
        manager = SessionManager(db_session)

        with pytest.raises(SessionNotFoundError):
            await manager.add_message(
                "nonexistent-uuid",
                role="user",
                content="Hello!",
            )

    async def test_get_messages(self, db_session: AsyncSession, project: Project):
        """Test getting messages from a session."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)

        await manager.add_message(session.id, "user", "First")
        await manager.add_message(session.id, "assistant", "Second")
        await manager.add_message(session.id, "user", "Third")

        messages = await manager.get_messages(session.id)

        assert len(messages) == 3
        assert [m.content for m in messages] == ["First", "Second", "Third"]

    async def test_get_messages_with_limit(
        self, db_session: AsyncSession, project: Project
    ):
        """Test getting messages with a limit."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)

        for i in range(5):
            await manager.add_message(session.id, "user", f"Message {i}")

        messages = await manager.get_messages(session.id, limit=3)

        assert len(messages) == 3

    async def test_get_messages_since(self, db_session: AsyncSession, project: Project):
        """Test getting messages since a timestamp."""
        import asyncio

        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)

        await manager.add_message(session.id, "user", "Old message")
        await asyncio.sleep(0.01)

        cutoff = datetime.now(timezone.utc)
        await asyncio.sleep(0.01)

        await manager.add_message(session.id, "user", "New message")

        messages = await manager.get_messages(session.id, since=cutoff)

        assert len(messages) == 1
        assert messages[0].content == "New message"

    # Cost Tracking Tests

    async def test_update_session_cost(
        self, db_session: AsyncSession, project: Project
    ):
        """Test updating session cost."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)

        await manager.update_session_cost(session.id, 0.01)
        await manager.update_session_cost(session.id, 0.02)

        updated = await manager.get_session(session.id)
        assert updated.total_cost_usd == pytest.approx(0.03)

    # Claude Session ID Tests

    async def test_set_claude_session_id(
        self, db_session: AsyncSession, project: Project
    ):
        """Test setting Claude's session ID on transition."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)

        updated = await manager.update_session_status(
            session.id,
            SessionStatus.RUNNING,
            claude_session_id="claude-session-xyz",
        )

        assert updated.claude_session_id == "claude-session-xyz"

    async def test_pending_approval_requires_running(
        self, db_session: AsyncSession, project: Project
    ):
        """Test that setting pending approval requires RUNNING state."""
        manager = SessionManager(db_session)

        session = await manager.create_session(project_id=project.id)

        with pytest.raises(SessionStateError, match="RUNNING state"):
            await manager.set_pending_approval(
                session.id,
                {
                    "tool_name": "Write",
                    "tool_input": {},
                    "tool_use_id": "toolu_123",
                    "requested_at": "2026-02-06T00:00:00+00:00",
                },
            )
