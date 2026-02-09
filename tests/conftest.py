"""Pytest configuration and fixtures for ZURK tests."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from unittest.mock import AsyncMock, MagicMock

from src.models import Base, Project, Session, SessionStatus, Message
from src.api.app import create_app
from src.models.base import get_db
from src.api.deps import get_agent_runtime, get_approval_handler_dep, reset_agent_runtime, reset_background_engine
from src.core.approval_handler import ApprovalHandler, reset_approval_handler
from src.config import Settings


@pytest.fixture
async def db_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncSession:
    """Create a database session for testing."""
    factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        yield session


@pytest.fixture
def sample_project_data() -> dict:
    """Sample data for creating a project."""
    return {
        "name": "Test Project",
        "path": "/home/user/projects/test-project",
        "description": "A test project for unit tests",
        "default_allowed_tools": ["Read", "Write", "Bash"],
        "permission_mode": "default",
        "auto_approve_patterns": ["git status", "npm test"],
    }


@pytest.fixture
async def sample_project(db_session: AsyncSession, sample_project_data: dict) -> Project:
    """Create and return a sample project in the database."""
    project = Project(**sample_project_data)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.fixture
def sample_session_data(sample_project: Project) -> dict:
    """Sample data for creating a session."""
    return {
        "project_id": sample_project.id,
        "name": "Test Session",
        "status": SessionStatus.IDLE.value,
        "last_prompt": "Hello, Claude!",
    }


@pytest.fixture
async def sample_session(
    db_session: AsyncSession,
    sample_project: Project,
    sample_session_data: dict,
) -> Session:
    """Create and return a sample session in the database."""
    session_obj = Session(**sample_session_data)
    db_session.add(session_obj)
    await db_session.commit()
    await db_session.refresh(session_obj)
    return session_obj


@pytest.fixture
def sample_message_data(sample_session: Session) -> dict:
    """Sample data for creating a message."""
    return {
        "session_id": sample_session.id,
        "role": "user",
        "content": "Hello, Claude!",
        "message_type": "user",
        "extra": {"tokens": 5},
    }


@pytest.fixture
async def sample_message(
    db_session: AsyncSession,
    sample_session: Session,
    sample_message_data: dict,
) -> Message:
    """Create and return a sample message in the database."""
    message = Message(**sample_message_data)
    db_session.add(message)
    await db_session.commit()
    await db_session.refresh(message)
    return message


# =============================================================================
# API Test Fixtures
# =============================================================================


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        debug=True,
        cors_origins=["*"],
        default_model="claude-sonnet-4-5",
        default_permission_mode="default",
    )


def _mock_async_gen_factory():
    """Factory that returns a new empty async generator each time."""
    async def _gen():
        return
        yield  # Makes this an async generator
    return _gen()


@pytest.fixture
def mock_agent_runtime() -> MagicMock:
    """Create a mock AgentRuntime for API tests."""
    runtime = MagicMock()
    # These methods return async iterators - use side_effect to return fresh gen each time
    runtime.start_session = MagicMock(side_effect=lambda *args, **kwargs: _mock_async_gen_factory())
    runtime.resume_session = MagicMock(side_effect=lambda *args, **kwargs: _mock_async_gen_factory())
    runtime.send_prompt = MagicMock(side_effect=lambda *args, **kwargs: _mock_async_gen_factory())
    runtime.interrupt_session = AsyncMock()
    runtime.disconnect_session = AsyncMock()
    runtime.cleanup = AsyncMock()
    runtime.is_session_active = MagicMock(return_value=False)
    runtime.get_claude_session_id = MagicMock(return_value=None)
    return runtime


@pytest.fixture
async def api_client(db_engine, mock_agent_runtime, test_settings, monkeypatch):
    """Create an httpx AsyncClient for API testing.

    This fixture:
    - Creates a test database (in-memory)
    - Overrides dependencies to use test database
    - Patches AgentOrchestrator methods to be no-ops (they use separate DB)
    - Provides an async client for making requests
    """
    # Create session factory for this test
    factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create the app
    app = create_app(test_settings)

    # Override database dependency
    async def override_get_db():
        async with factory() as session:
            yield session

    # Override agent runtime dependency
    def override_get_agent_runtime(settings=None):
        return mock_agent_runtime

    # Override approval handler dependency
    test_approval_handler = ApprovalHandler()

    async def override_get_approval_handler():
        return test_approval_handler

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_agent_runtime] = override_get_agent_runtime
    app.dependency_overrides[get_approval_handler_dep] = override_get_approval_handler

    # Patch AgentOrchestrator methods to be no-ops
    # Background tasks use separate DB sessions which don't work with in-memory SQLite
    async def noop_start_session(*args, **kwargs):
        pass

    async def noop_resume_session(*args, **kwargs):
        pass

    monkeypatch.setattr(
        "src.services.agent_orchestrator.AgentOrchestrator.start_session",
        noop_start_session,
    )
    monkeypatch.setattr(
        "src.services.agent_orchestrator.AgentOrchestrator.resume_session",
        noop_resume_session,
    )

    # Reset singletons
    reset_agent_runtime()
    reset_background_engine()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    # Cleanup
    app.dependency_overrides.clear()
    reset_agent_runtime()
    reset_background_engine()
    reset_approval_handler()


@pytest.fixture
async def api_client_with_project(api_client, sample_project_data):
    """API client with a pre-created project."""
    # Modify path to use temp dir for validation
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        project_data = {**sample_project_data, "path": tmpdir, "validate_path": True}
        response = await api_client.post("/projects", json=project_data)
        assert response.status_code == 201
        project = response.json()
        yield api_client, project
