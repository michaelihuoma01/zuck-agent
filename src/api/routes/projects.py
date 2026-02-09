"""Project management routes."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status, BackgroundTasks

from src.api.deps import (
    ProjectRegistryDep,
    SessionManagerDep,
    AgentRuntimeDep,
    ApprovalHandlerDep,
    ApiKeyDep,
)
from src.api.schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectListResponse,
    PreviewStatusResponse,
    SessionResponse,
    ExternalSessionResponse,
    ExternalSessionListResponse,
    ExternalMessageResponse,
    ExternalSessionDetailResponse,
    ContinueExternalSessionRequest,
    ErrorResponse,
)
from src.core.exceptions import (
    ProjectNotFoundError,
    ProjectPathExistsError,
    ProjectPathInvalidError,
    ProjectValidationError,
)
from src.services.agent_orchestrator import AgentOrchestrator
from src.services.preview_manager import get_preview_manager
from src.utils.session_discovery import (
    discover_sessions,
    encode_project_path,
    CLAUDE_PROJECTS_DIR,
)
from src.utils.session_reader import read_session_messages

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get(
    "",
    response_model=ProjectListResponse,
    summary="List all projects",
)
async def list_projects(
    registry: ProjectRegistryDep,
    _api_key: ApiKeyDep,
) -> ProjectListResponse:
    """List all registered projects.

    Returns projects ordered by name.
    """
    projects = await registry.list_projects()
    return ProjectListResponse(
        projects=[ProjectResponse.model_validate(p) for p in projects],
        total=len(projects),
    )


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new project",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid project data"},
        409: {"model": ErrorResponse, "description": "Project path already registered"},
    },
)
async def create_project(
    project: ProjectCreate,
    registry: ProjectRegistryDep,
    _api_key: ApiKeyDep,
) -> ProjectResponse:
    """Register a new project directory.

    The path must be an absolute path to an existing directory.
    If validate_path is False, the path existence check is skipped.
    """
    try:
        created = await registry.register_project(
            name=project.name,
            path=project.path,
            description=project.description,
            default_allowed_tools=project.default_allowed_tools,
            permission_mode=project.permission_mode,
            auto_approve_patterns=project.auto_approve_patterns,
            validate_path=project.validate_path,
            dev_command=project.dev_command,
            dev_port=project.dev_port,
        )
        return ProjectResponse.model_validate(created)

    except ProjectPathExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except ProjectPathInvalidError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ProjectValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get project details",
    responses={
        404: {"model": ErrorResponse, "description": "Project not found"},
    },
)
async def get_project(
    project_id: str,
    registry: ProjectRegistryDep,
    _api_key: ApiKeyDep,
) -> ProjectResponse:
    """Get a project by ID."""
    try:
        project = await registry.get_project(project_id)
        return ProjectResponse.model_validate(project)
    except ProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update project settings",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid project data"},
        404: {"model": ErrorResponse, "description": "Project not found"},
    },
)
async def update_project(
    project_id: str,
    update: ProjectUpdate,
    registry: ProjectRegistryDep,
    _api_key: ApiKeyDep,
) -> ProjectResponse:
    """Update a project's settings.

    Only fields that are provided will be updated.
    """
    try:
        updated = await registry.update_project(
            project_id=project_id,
            name=update.name,
            description=update.description,
            default_allowed_tools=update.default_allowed_tools,
            permission_mode=update.permission_mode,
            auto_approve_patterns=update.auto_approve_patterns,
            dev_command=update.dev_command,
            dev_port=update.dev_port,
        )
        return ProjectResponse.model_validate(updated)

    except ProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ProjectValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unregister a project",
    responses={
        404: {"model": ErrorResponse, "description": "Project not found"},
    },
)
async def delete_project(
    project_id: str,
    registry: ProjectRegistryDep,
    _api_key: ApiKeyDep,
) -> None:
    """Unregister a project and delete all its sessions.

    This action is irreversible. All session data for this project
    will be permanently deleted.
    """
    try:
        await registry.delete_project(project_id)
    except ProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/{project_id}/preview/start",
    response_model=PreviewStatusResponse,
    summary="Start live preview dev server",
    responses={
        400: {"model": ErrorResponse, "description": "No dev_command configured"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        409: {"model": ErrorResponse, "description": "Preview already running"},
    },
)
async def start_preview(
    project_id: str,
    registry: ProjectRegistryDep,
    _api_key: ApiKeyDep,
) -> PreviewStatusResponse:
    try:
        project = await registry.get_project(project_id)
    except ProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    if not project.dev_command:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No dev_command configured for this project",
        )

    mgr = get_preview_manager()
    result = await mgr.start_preview(project)
    return PreviewStatusResponse(
        running=result.running,
        url=result.url,
        port=result.port,
        pid=result.pid,
        uptime_seconds=result.uptime_seconds,
        project_type=result.project_type,
        error=result.error,
    )


@router.post(
    "/{project_id}/preview/stop",
    response_model=PreviewStatusResponse,
    summary="Stop live preview dev server",
    responses={
        404: {"model": ErrorResponse, "description": "Project or preview not found"},
    },
)
async def stop_preview(
    project_id: str,
    registry: ProjectRegistryDep,
    _api_key: ApiKeyDep,
) -> PreviewStatusResponse:
    try:
        await registry.get_project(project_id)
    except ProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    mgr = get_preview_manager()
    existing = mgr.get_status(project_id)
    if not existing.running:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No preview running for this project",
        )

    result = await mgr.stop_preview(project_id)
    return PreviewStatusResponse(
        running=result.running,
        url=result.url,
        port=result.port,
        pid=result.pid,
        uptime_seconds=result.uptime_seconds,
        project_type=result.project_type,
        error=result.error,
    )


@router.get(
    "/{project_id}/preview/status",
    response_model=PreviewStatusResponse,
    summary="Get live preview status",
    responses={
        404: {"model": ErrorResponse, "description": "Project not found"},
    },
)
async def get_preview_status(
    project_id: str,
    registry: ProjectRegistryDep,
    _api_key: ApiKeyDep,
) -> PreviewStatusResponse:
    try:
        await registry.get_project(project_id)
    except ProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    result = get_preview_manager().get_status(project_id)
    return PreviewStatusResponse(
        running=result.running,
        url=result.url,
        port=result.port,
        pid=result.pid,
        uptime_seconds=result.uptime_seconds,
        project_type=result.project_type,
        error=result.error,
    )


@router.get(
    "/{project_id}/validate",
    summary="Validate project path",
    responses={
        404: {"model": ErrorResponse, "description": "Project not found"},
    },
)
async def validate_project_path(
    project_id: str,
    registry: ProjectRegistryDep,
    _api_key: ApiKeyDep,
) -> dict:
    """Check if a project's path still exists and is accessible."""
    try:
        is_valid = await registry.validate_project_path(project_id)
        return {"valid": is_valid}
    except ProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/{project_id}/external-sessions",
    response_model=ExternalSessionListResponse,
    summary="Discover Claude Code sessions from the local filesystem",
    responses={
        404: {"model": ErrorResponse, "description": "Project not found"},
    },
)
async def list_external_sessions(
    project_id: str,
    registry: ProjectRegistryDep,
    _api_key: ApiKeyDep,
) -> ExternalSessionListResponse:
    """Discover Claude Code sessions stored locally for this project.

    Scans ~/.claude/projects/<encoded-path>/ for JSONL session files
    that were created by Claude Code (VS Code, CLI, etc.) and returns
    their metadata without importing them into ZURK.
    """
    try:
        project = await registry.get_project(project_id)
    except ProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    sessions = discover_sessions(project.path)
    encoded = encode_project_path(project.path)
    claude_dir = str(CLAUDE_PROJECTS_DIR / encoded)

    return ExternalSessionListResponse(
        sessions=[
            ExternalSessionResponse(
                session_id=s.session_id,
                file_path=s.file_path,
                file_size_bytes=s.file_size_bytes,
                slug=s.slug,
                started_at=s.started_at,
                ended_at=s.ended_at,
                model=s.model,
                claude_code_version=s.claude_code_version,
                total_entries=s.total_entries,
                user_messages=s.user_messages,
                assistant_messages=s.assistant_messages,
                has_subagents=s.has_subagents,
                cwd=s.cwd,
                git_branch=s.git_branch,
                title=s.title,
            )
            for s in sessions
        ],
        total=len(sessions),
        project_path=project.path,
        claude_dir=claude_dir,
    )


def _resolve_session_file(project_path: str, session_id: str) -> Path:
    """Resolve the JSONL file path for an external session.

    Raises HTTPException(404) if the file does not exist.
    """
    encoded = encode_project_path(project_path)
    file_path = CLAUDE_PROJECTS_DIR / encoded / f"{session_id}.jsonl"
    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session file not found: {session_id}",
        )
    return file_path


def _read_claude_session_id(file_path: Path) -> str:
    """Read Claude's real sessionId from the first JSONL entry.

    Falls back to the filename stem if the field is missing.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline().strip()
            if first_line:
                entry = json.loads(first_line)
                return entry.get("sessionId", file_path.stem)
    except (json.JSONDecodeError, OSError):
        pass
    return file_path.stem


@router.get(
    "/{project_id}/external-sessions/{session_id}",
    response_model=ExternalSessionDetailResponse,
    summary="View an external Claude Code session's messages",
    responses={
        404: {"model": ErrorResponse, "description": "Project or session not found"},
    },
)
async def get_external_session(
    project_id: str,
    session_id: str,
    registry: ProjectRegistryDep,
    _api_key: ApiKeyDep,
) -> ExternalSessionDetailResponse:
    """Parse a Claude Code JSONL session file and return its full message history.

    This is a read-only view — ZURK never modifies the original session file.
    """
    try:
        project = await registry.get_project(project_id)
    except ProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    file_path = _resolve_session_file(project.path, session_id)

    try:
        meta, messages = read_session_messages(file_path)
    except OSError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read session file: {e}",
        )

    return ExternalSessionDetailResponse(
        session_id=meta.session_id,
        slug=meta.slug,
        model=meta.model,
        claude_code_version=meta.claude_code_version,
        started_at=meta.started_at,
        ended_at=meta.ended_at,
        messages=[
            ExternalMessageResponse(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                message_type=m.message_type,
                metadata=m.metadata,
                timestamp=m.timestamp,
            )
            for m in messages
        ],
        total_messages=len(messages),
    )


@router.post(
    "/{project_id}/external-sessions/{session_id}/continue",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Continue an external Claude Code session inside ZURK",
    responses={
        404: {"model": ErrorResponse, "description": "Project or session not found"},
    },
)
async def continue_external_session(
    project_id: str,
    session_id: str,
    body: ContinueExternalSessionRequest,
    registry: ProjectRegistryDep,
    manager: SessionManagerDep,
    runtime: AgentRuntimeDep,
    approval_handler: ApprovalHandlerDep,
    background_tasks: BackgroundTasks,
    _api_key: ApiKeyDep,
) -> SessionResponse:
    """Create a new ZURK session that resumes an external Claude Code session.

    The external session file is never modified. A new ZURK session record is
    created with ``claude_session_id`` set to the external session's ID, and
    ``orchestrator.resume_session()`` is started in the background.
    """
    try:
        project = await registry.get_project(project_id)
    except ProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    file_path = _resolve_session_file(project.path, session_id)
    claude_sid = _read_claude_session_id(file_path)

    # Create ZURK session with the external Claude session ID pre-set
    session = await manager.create_session(
        project_id=project_id,
        name=body.name,
        initial_prompt=body.prompt,
        claude_session_id=claude_sid,
    )

    # Start resumption in background
    orchestrator = AgentOrchestrator(runtime, approval_handler=approval_handler)
    background_tasks.add_task(
        orchestrator.resume_session,
        project=project,
        session_id=session.id,
        claude_session_id=claude_sid,
        prompt=body.prompt,
    )

    # Refresh to include the claude_session_id
    session = await manager.get_session(session.id)
    return SessionResponse.model_validate(session)
