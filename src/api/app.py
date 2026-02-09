"""FastAPI application factory for ZURK."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text

import logging

from src.config import Settings, get_settings
from src.logging_config import setup_logging
from src.models import init_db, close_db
from src.models.base import get_engine, get_session_factory
from src.models.project import Project
from src.api.deps import reset_agent_runtime
from src.services.preview_manager import get_preview_manager
from src.utils.project_detector import detect_project_type

logger = logging.getLogger(__name__)

# Import routers
from src.api.routes.health import router as health_router
from src.api.routes.projects import router as projects_router
from src.api.routes.sessions import router as sessions_router
from src.api.routes.filesystem import router as filesystem_router
from src.api.websocket.session_stream import router as websocket_router


async def _run_migrations() -> None:
    """Add new columns if they don't exist (idempotent)."""
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(projects)"))
        columns = {row[1] for row in result.fetchall()}
        if "dev_command" not in columns:
            await conn.execute(text("ALTER TABLE projects ADD COLUMN dev_command TEXT"))
        if "dev_port" not in columns:
            await conn.execute(text("ALTER TABLE projects ADD COLUMN dev_port INTEGER"))


async def _backfill_dev_commands() -> None:
    """Auto-detect dev commands for all projects (backfill NULL + fix stale detections)."""
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Project))
        all_projects = result.scalars().all()
        if not all_projects:
            return

        updated = 0
        for project in all_projects:
            cmd, port, _ = detect_project_type(project.path)
            if cmd and (project.dev_command != cmd or project.dev_port != port):
                project.dev_command = cmd
                project.dev_port = port
                updated += 1

        if updated:
            await session.commit()
            logger.info("Updated dev_command for %d project(s)", updated)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan - startup and shutdown.

    Handles:
    - Database initialization on startup
    - Database migrations
    - Preview orphan recovery
    - Agent runtime cleanup on shutdown
    - Preview cleanup on shutdown
    - Database connection cleanup on shutdown
    """
    # Startup
    setup_logging(debug=get_settings().debug)
    await init_db()
    await _run_migrations()
    await _backfill_dev_commands()
    get_preview_manager()._recover_orphans()
    yield
    # Shutdown
    await get_preview_manager().cleanup_all()
    reset_agent_runtime()
    await close_db()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Optional settings override. Uses get_settings() if not provided.

    Returns:
        Configured FastAPI application instance.
    """
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title="ZURK - Agent Command Center",
        description="Centralized orchestration system for managing Claude Code sessions remotely",
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "health", "description": "Health check endpoints"},
            {"name": "projects", "description": "Project management"},
            {"name": "sessions", "description": "Agent session management"},
            {"name": "websocket", "description": "Real-time WebSocket streaming"},
            {"name": "filesystem", "description": "Filesystem browsing for folder picker"},
        ],
    )

    # CORS middleware for frontend access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routers
    app.include_router(health_router)
    app.include_router(projects_router)
    app.include_router(sessions_router)
    app.include_router(filesystem_router)
    app.include_router(websocket_router)

    # Root endpoint
    @app.get("/", tags=["root"])
    async def root():
        """Root endpoint with API info."""
        return {
            "name": "ZURK - Agent Command Center",
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/health",
        }

    return app
