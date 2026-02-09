"""Tests for database models."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Project, Session, SessionStatus, Message


class TestProjectModel:
    """Tests for the Project model."""

    async def test_create_project(
        self, db_session: AsyncSession, sample_project_data: dict
    ):
        """Test creating a project."""
        project = Project(**sample_project_data)
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)

        assert project.id is not None
        assert len(project.id) == 36  # UUID length
        assert project.name == sample_project_data["name"]
        assert project.path == sample_project_data["path"]
        assert project.description == sample_project_data["description"]
        assert project.permission_mode == "default"
        assert project.created_at is not None
        assert project.updated_at is not None

    async def test_project_default_values(self, db_session: AsyncSession):
        """Test project default values."""
        project = Project(name="Minimal Project", path="/tmp/minimal")
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)

        assert project.permission_mode == "default"
        assert project.description is None
        assert project.default_allowed_tools == []
        assert project.auto_approve_patterns == []

    async def test_project_to_dict(self, sample_project: Project):
        """Test project to_dict method."""
        data = sample_project.to_dict()

        assert data["id"] == sample_project.id
        assert data["name"] == sample_project.name
        assert data["path"] == sample_project.path
        assert "created_at" in data
        assert "updated_at" in data

    async def test_project_unique_path(
        self, db_session: AsyncSession, sample_project: Project
    ):
        """Test that project paths must be unique."""
        duplicate = Project(name="Duplicate", path=sample_project.path)
        db_session.add(duplicate)

        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()

    async def test_read_project(
        self, db_session: AsyncSession, sample_project: Project
    ):
        """Test reading a project from database."""
        result = await db_session.execute(
            select(Project).where(Project.id == sample_project.id)
        )
        fetched = result.scalar_one()

        assert fetched.id == sample_project.id
        assert fetched.name == sample_project.name

    async def test_update_project(
        self, db_session: AsyncSession, sample_project: Project
    ):
        """Test updating a project."""
        sample_project.name = "Updated Name"
        sample_project.permission_mode = "acceptEdits"
        await db_session.commit()
        await db_session.refresh(sample_project)

        assert sample_project.name == "Updated Name"
        assert sample_project.permission_mode == "acceptEdits"

    async def test_delete_project(
        self, db_session: AsyncSession, sample_project: Project
    ):
        """Test deleting a project."""
        project_id = sample_project.id
        await db_session.delete(sample_project)
        await db_session.commit()

        result = await db_session.execute(
            select(Project).where(Project.id == project_id)
        )
        assert result.scalar_one_or_none() is None


class TestSessionModel:
    """Tests for the Session model."""

    async def test_create_session(
        self, db_session: AsyncSession, sample_project: Project
    ):
        """Test creating a session."""
        session_obj = Session(
            project_id=sample_project.id,
            name="My Session",
            last_prompt="Hello!",
        )
        db_session.add(session_obj)
        await db_session.commit()
        await db_session.refresh(session_obj)

        assert session_obj.id is not None
        assert session_obj.project_id == sample_project.id
        assert session_obj.status == SessionStatus.IDLE.value
        assert session_obj.message_count == 0
        assert session_obj.total_cost_usd == 0.0

    async def test_session_status_enum(self, sample_session: Session):
        """Test session status enum helpers."""
        assert sample_session.status_enum == SessionStatus.IDLE

        sample_session.set_status(SessionStatus.RUNNING)
        assert sample_session.status == "running"
        assert sample_session.status_enum == SessionStatus.RUNNING

    async def test_session_pending_approval(
        self, db_session: AsyncSession, sample_session: Session
    ):
        """Test session pending approval JSON field."""
        sample_session.pending_approval = {
            "tool_name": "Write",
            "tool_input": {"path": "test.py", "content": "print('hello')"},
            "tool_use_id": "toolu_123",
            "file_path": "test.py",
            "diff": "+print('hello')",
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }
        sample_session.set_status(SessionStatus.WAITING_APPROVAL)
        await db_session.commit()
        await db_session.refresh(sample_session)

        assert sample_session.pending_approval["tool_name"] == "Write"
        assert sample_session.status_enum == SessionStatus.WAITING_APPROVAL

    async def test_session_to_dict(self, sample_session: Session):
        """Test session to_dict method."""
        data = sample_session.to_dict()

        assert data["id"] == sample_session.id
        assert data["project_id"] == sample_session.project_id
        assert data["status"] == "idle"
        assert "messages" not in data  # Default excludes messages

    async def test_session_to_dict_with_messages(
        self, db_session: AsyncSession, sample_session: Session
    ):
        """Test session to_dict with messages included."""
        from sqlalchemy.orm import selectinload

        # Add a message
        message = Message(
            session_id=sample_session.id,
            role="user",
            content="Hello!",
        )
        db_session.add(message)
        await db_session.commit()

        # Reload with eager loading for async compatibility
        result = await db_session.execute(
            select(Session)
            .options(selectinload(Session.messages))
            .where(Session.id == sample_session.id)
        )
        loaded_session = result.scalar_one()

        data = loaded_session.to_dict(include_messages=True)
        assert "messages" in data
        assert len(data["messages"]) == 1

    async def test_session_project_relationship(
        self, db_session: AsyncSession, sample_session: Session, sample_project: Project
    ):
        """Test session-project relationship."""
        # Access project through session
        await db_session.refresh(sample_session)
        assert sample_session.project_id == sample_project.id

    async def test_cascade_delete_sessions(
        self, db_session: AsyncSession, sample_project: Project
    ):
        """Test that deleting a project cascades to sessions."""
        # Create a session
        session_obj = Session(project_id=sample_project.id, name="Will be deleted")
        db_session.add(session_obj)
        await db_session.commit()
        session_id = session_obj.id

        # Delete the project
        await db_session.delete(sample_project)
        await db_session.commit()

        # Session should be gone
        result = await db_session.execute(
            select(Session).where(Session.id == session_id)
        )
        assert result.scalar_one_or_none() is None


class TestMessageModel:
    """Tests for the Message model."""

    async def test_create_message(
        self, db_session: AsyncSession, sample_session: Session
    ):
        """Test creating a message."""
        message = Message(
            session_id=sample_session.id,
            role="assistant",
            content="Hello! How can I help you?",
            message_type="assistant",
            extra={"tokens": 10},
        )
        db_session.add(message)
        await db_session.commit()
        await db_session.refresh(message)

        assert message.id is not None
        assert message.session_id == sample_session.id
        assert message.role == "assistant"
        assert message.timestamp is not None

    async def test_message_roles(
        self, db_session: AsyncSession, sample_session: Session
    ):
        """Test various message roles."""
        roles = ["user", "assistant", "system", "tool_use", "tool_result"]

        for role in roles:
            message = Message(
                session_id=sample_session.id,
                role=role,
                content=f"Test {role} message",
            )
            db_session.add(message)

        await db_session.commit()

        result = await db_session.execute(
            select(Message).where(Message.session_id == sample_session.id)
        )
        messages = result.scalars().all()
        assert len(messages) == len(roles)

    async def test_message_to_dict(self, sample_message: Message):
        """Test message to_dict method."""
        data = sample_message.to_dict()

        assert data["id"] == sample_message.id
        assert data["session_id"] == sample_message.session_id
        assert data["role"] == "user"
        assert data["content"] == "Hello, Claude!"
        assert data["metadata"] == {"tokens": 5}  # Exposed as "metadata" in API

    async def test_message_ordering(
        self, db_session: AsyncSession, sample_session: Session
    ):
        """Test that messages are ordered by timestamp."""
        import asyncio
        from sqlalchemy.orm import selectinload

        for i in range(3):
            message = Message(
                session_id=sample_session.id,
                role="user",
                content=f"Message {i}",
            )
            db_session.add(message)
            await db_session.commit()
            await asyncio.sleep(0.01)  # Small delay for timestamp ordering

        # Reload with eager loading for async compatibility
        result = await db_session.execute(
            select(Session)
            .options(selectinload(Session.messages))
            .where(Session.id == sample_session.id)
        )
        loaded_session = result.scalar_one()

        # Messages should be in order
        contents = [m.content for m in loaded_session.messages]
        assert contents == ["Message 0", "Message 1", "Message 2"]

    async def test_cascade_delete_messages(
        self, db_session: AsyncSession, sample_session: Session
    ):
        """Test that deleting a session cascades to messages."""
        # Create messages
        for i in range(3):
            message = Message(
                session_id=sample_session.id,
                role="user",
                content=f"Message {i}",
            )
            db_session.add(message)
        await db_session.commit()

        session_id = sample_session.id

        # Delete the session
        await db_session.delete(sample_session)
        await db_session.commit()

        # Messages should be gone
        result = await db_session.execute(
            select(Message).where(Message.session_id == session_id)
        )
        assert len(result.scalars().all()) == 0

    async def test_message_repr(self, sample_message: Message):
        """Test message __repr__ method."""
        repr_str = repr(sample_message)
        assert "Message" in repr_str
        assert sample_message.role in repr_str
