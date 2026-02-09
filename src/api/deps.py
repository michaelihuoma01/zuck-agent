"""FastAPI dependencies for dependency injection."""

import threading
from typing import Annotated, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import Settings, get_settings
from src.models.base import get_db
from src.core.project_registry import ProjectRegistry
from src.core.session_manager import SessionManager
from src.core.agent_runtime import AgentRuntime
from src.core.approval_handler import ApprovalHandler, get_approval_handler

# Re-export security dependencies for convenience
from src.api.security import (
    ApiKeyDep,
    WebSocketApiKeyDep,
    OptionalApiKeyDep,
    verify_api_key,
    verify_websocket_api_key,
)

__all__ = [
    "DBSession",
    "AppSettings",
    "ProjectRegistryDep",
    "SessionManagerDep",
    "AgentRuntimeDep",
    "ApprovalHandlerDep",
    "ApiKeyDep",
    "WebSocketApiKeyDep",
    "OptionalApiKeyDep",
    "get_background_db_session",
    "reset_agent_runtime",
]


# Type aliases for cleaner dependency injection
DBSession = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


async def get_project_registry(db: DBSession) -> ProjectRegistry:
    """Get ProjectRegistry instance with database session."""
    return ProjectRegistry(db)


async def get_session_manager(db: DBSession) -> SessionManager:
    """Get SessionManager instance with database session."""
    return SessionManager(db)


# Thread-safe singleton for AgentRuntime
_agent_runtime: AgentRuntime | None = None
_runtime_lock = threading.Lock()


def get_agent_runtime(settings: AppSettings) -> AgentRuntime:
    """Get or create the singleton AgentRuntime instance.

    The runtime is a singleton because it maintains active client
    connections that need to persist across requests.

    This implementation is thread-safe using a lock to prevent
    race conditions during initialization.
    """
    global _agent_runtime

    # Fast path: already initialized
    if _agent_runtime is not None:
        return _agent_runtime

    # Slow path: need to initialize with lock
    with _runtime_lock:
        # Double-check after acquiring lock
        if _agent_runtime is None:
            _agent_runtime = AgentRuntime(settings)
        return _agent_runtime


def reset_agent_runtime() -> None:
    """Reset the agent runtime. Use only in tests or shutdown."""
    global _agent_runtime
    with _runtime_lock:
        if _agent_runtime is not None:
            # Note: cleanup() should be called before reset in production
            _agent_runtime = None


# =============================================================================
# Background Task Database Sessions
# =============================================================================
# Background tasks run AFTER the request completes, so they cannot use
# the request's database session (it will be closed). They must create
# their own sessions.

_background_engine = None
_background_session_factory = None
_engine_lock = threading.Lock()


def _get_background_session_factory() -> async_sessionmaker:
    """Get or create a session factory for background tasks."""
    global _background_engine, _background_session_factory

    if _background_session_factory is not None:
        return _background_session_factory

    with _engine_lock:
        if _background_session_factory is None:
            settings = get_settings()
            _background_engine = create_async_engine(
                settings.database_url,
                echo=settings.debug,
            )
            _background_session_factory = async_sessionmaker(
                _background_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return _background_session_factory


async def get_background_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a new database session for background tasks.

    Unlike get_db(), this creates a completely independent session
    that won't be closed when the request completes.

    Usage in background tasks:
        async with get_background_db_session() as db:
            manager = SessionManager(db)
            await manager.update_session_status(...)
    """
    factory = _get_background_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


def reset_background_engine() -> None:
    """Reset the background engine. Use only in tests."""
    global _background_engine, _background_session_factory
    with _engine_lock:
        _background_engine = None
        _background_session_factory = None


async def get_approval_handler_dep() -> ApprovalHandler:
    """Get the global ApprovalHandler instance."""
    return await get_approval_handler()


# Annotated types for dependency injection
ProjectRegistryDep = Annotated[ProjectRegistry, Depends(get_project_registry)]
SessionManagerDep = Annotated[SessionManager, Depends(get_session_manager)]
AgentRuntimeDep = Annotated[AgentRuntime, Depends(get_agent_runtime)]
ApprovalHandlerDep = Annotated[ApprovalHandler, Depends(get_approval_handler_dep)]
