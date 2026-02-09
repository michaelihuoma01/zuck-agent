"""Session management routes."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse

from src.api.deps import (
    SessionManagerDep,
    ProjectRegistryDep,
    AgentRuntimeDep,
    ApprovalHandlerDep,
    ApiKeyDep,
)
from src.api.schemas import (
    SessionCreate,
    SessionResponse,
    SessionWithMessagesResponse,
    SessionListResponse,
    SessionPrompt,
    SessionApproval,
    SessionApprovalResponse,
    MessageResponse,
    MessageListResponse,
    ErrorResponse,
    GlobalExternalSessionResponse,
    GlobalExternalSessionListResponse,
)
from src.models import SessionStatus
from src.core.constants import MessageType
from src.core.exceptions import (
    SessionNotFoundError,
    SessionStateError,
    ProjectNotFoundError,
)
from src.services.agent_orchestrator import AgentOrchestrator, broadcast_approval_processed
from src.utils.session_discovery import discover_sessions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


# =============================================================================
# List & Create Sessions
# =============================================================================


@router.get(
    "",
    response_model=SessionListResponse,
    summary="List sessions",
)
async def list_sessions(
    manager: SessionManagerDep,
    _api_key: ApiKeyDep,  # Require authentication
    project_id: str | None = None,
    session_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> SessionListResponse:
    """List sessions with optional filters.

    Args:
        project_id: Filter by project
        session_status: Filter by status (idle, running, waiting_approval, completed, error)
        limit: Maximum number of results (default 50)
        offset: Number of results to skip
    """
    status_enum = None
    if session_status:
        try:
            status_enum = SessionStatus(session_status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {session_status}. Valid: {[s.value for s in SessionStatus]}",
            )

    sessions, total = await manager.list_sessions_with_count(
        project_id=project_id,
        status=status_enum,
        limit=limit,
        offset=offset,
    )

    return SessionListResponse(
        sessions=[SessionResponse.model_validate(s) for s in sessions],
        total=total,
    )


@router.get(
    "/external",
    response_model=GlobalExternalSessionListResponse,
    summary="List external Claude Code sessions across all projects",
)
async def list_all_external_sessions(
    registry: ProjectRegistryDep,
    _api_key: ApiKeyDep,
    limit: int = 50,
) -> GlobalExternalSessionListResponse:
    """Discover Claude Code sessions across all registered projects.

    Scans each project's Claude Code directory and returns sessions
    enriched with project context, sorted by started_at descending.
    """
    projects = await registry.list_projects()
    all_sessions: list[GlobalExternalSessionResponse] = []

    for project in projects:
        try:
            sessions = discover_sessions(project.path)
        except OSError:
            logger.warning(f"Failed to scan sessions for project {project.name}")
            continue

        for s in sessions:
            all_sessions.append(
                GlobalExternalSessionResponse(
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
                    project_id=project.id,
                    project_name=project.name,
                )
            )

    # Sort by started_at descending, cap at limit
    all_sessions.sort(key=lambda s: s.started_at or "", reverse=True)
    capped = all_sessions[:limit]

    return GlobalExternalSessionListResponse(
        sessions=capped,
        total=len(all_sessions),
    )


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new session and start agent",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid session data"},
        404: {"model": ErrorResponse, "description": "Project not found"},
    },
)
async def create_session(
    session_data: SessionCreate,
    manager: SessionManagerDep,
    registry: ProjectRegistryDep,
    runtime: AgentRuntimeDep,
    approval_handler: ApprovalHandlerDep,
    background_tasks: BackgroundTasks,
    _api_key: ApiKeyDep,
) -> SessionResponse:
    """Create a new session and start the Claude agent.

    The session is created immediately and the agent starts in the background.
    Use WebSocket or SSE endpoints to stream messages.
    """
    try:
        project = await registry.get_project(session_data.project_id)

        session = await manager.create_session(
            project_id=session_data.project_id,
            name=session_data.name,
            initial_prompt=session_data.prompt,
        )

        # Start agent in background with its own DB session
        orchestrator = AgentOrchestrator(runtime, approval_handler=approval_handler)
        background_tasks.add_task(
            orchestrator.start_session,
            project=project,
            session_id=session.id,
            prompt=session_data.prompt,
        )

        return SessionResponse.model_validate(session)

    except ProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# =============================================================================
# Session Operations
# =============================================================================


@router.get(
    "/{session_id}",
    response_model=SessionWithMessagesResponse,
    summary="Get session with message history",
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
)
async def get_session(
    session_id: str,
    manager: SessionManagerDep,
    _api_key: ApiKeyDep,
    include_messages: bool = True,
) -> SessionWithMessagesResponse:
    """Get a session by ID with optional message history."""
    try:
        session = await manager.get_session(session_id, include_messages=include_messages)
        response_data = SessionResponse.model_validate(session).model_dump()

        if include_messages:
            messages = await manager.get_messages(session_id)
            response_data["messages"] = [
                MessageResponse.model_validate(m) for m in messages
            ]
        else:
            response_data["messages"] = []

        return SessionWithMessagesResponse(**response_data)

    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/{session_id}/prompt",
    response_model=SessionResponse,
    summary="Send prompt to existing session",
    responses={
        400: {"model": ErrorResponse, "description": "Session not in valid state"},
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
)
async def send_prompt(
    session_id: str,
    prompt_data: SessionPrompt,
    manager: SessionManagerDep,
    registry: ProjectRegistryDep,
    runtime: AgentRuntimeDep,
    approval_handler: ApprovalHandlerDep,
    background_tasks: BackgroundTasks,
    _api_key: ApiKeyDep,
) -> SessionResponse:
    """Send a prompt to an existing session.

    The session must have an active connection (for follow-up) or
    a stored Claude session ID (for resume).
    """
    try:
        session = await manager.get_session(session_id)
        project = await registry.get_project(session.project_id)
        orchestrator = AgentOrchestrator(runtime, approval_handler=approval_handler)

        if session.claude_session_id:
            # Has a Claude session ID — resume the conversation
            background_tasks.add_task(
                orchestrator.resume_session,
                project=project,
                session_id=session_id,
                claude_session_id=session.claude_session_id,
                prompt=prompt_data.prompt,
            )
        else:
            # No Claude session ID — start fresh
            # (covers first turn or broken/crashed sessions)
            background_tasks.add_task(
                orchestrator.start_session,
                project=project,
                session_id=session_id,
                prompt=prompt_data.prompt,
            )

        # Refresh and return
        session = await manager.get_session(session_id)
        return SessionResponse.model_validate(session)

    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ProjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a session",
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
)
async def delete_session(
    session_id: str,
    manager: SessionManagerDep,
    runtime: AgentRuntimeDep,
    _api_key: ApiKeyDep,
) -> None:
    """Delete a session and all its messages."""
    try:
        # Disconnect agent if active
        if runtime.is_session_active(session_id):
            await runtime.disconnect_session(session_id)

        await manager.delete_session(session_id)

    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# =============================================================================
# Messages
# =============================================================================


@router.get(
    "/{session_id}/messages",
    response_model=MessageListResponse,
    summary="Get session messages",
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
)
async def get_session_messages(
    session_id: str,
    manager: SessionManagerDep,
    _api_key: ApiKeyDep,
    limit: int | None = None,
    offset: int = 0,
) -> MessageListResponse:
    """Get messages for a session with pagination."""
    try:
        messages, total = await manager.get_messages_with_count(
            session_id, limit=limit, offset=offset
        )
        return MessageListResponse(
            messages=[MessageResponse.model_validate(m) for m in messages],
            total=total,
        )
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# =============================================================================
# Approval Workflow
# =============================================================================


async def _process_approval_decision(
    session_id: str,
    approved: bool,
    feedback: str | None,
    manager: SessionManagerDep,
    approval_handler: ApprovalHandlerDep,
) -> None:
    """Shared logic for approve/deny: validate state, transition, signal hook.

    IMPORTANT: The DB status transition to RUNNING happens BEFORE signaling
    the event to avoid a race where the hook resumes and the agent completes
    before we update the status.

    Args:
        session_id: The session ID
        approved: Whether the tool was approved
        feedback: User feedback (required for denials)
        manager: Session manager for DB operations
        approval_handler: Handler with the pending request

    Raises:
        HTTPException: If session state is invalid or no pending request
    """
    session = await manager.get_session(session_id)

    if session.status_enum != SessionStatus.WAITING_APPROVAL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not waiting for approval",
        )

    # Transition session to RUNNING BEFORE signaling the hook.
    # This prevents a race where the hook resumes and the agent
    # completes (transitioning to COMPLETED) before we update status.
    await manager.update_session_status(session_id, SessionStatus.RUNNING)

    # Signal the waiting hook (unblocks the background task)
    processed = await approval_handler.process_decision(
        session_id=session_id,
        approved=approved,
        feedback=feedback,
    )

    if not processed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending approval request found in handler",
        )

    # Broadcast via WebSocket (non-blocking, best-effort)
    await broadcast_approval_processed(session_id, approved=approved, feedback=feedback)


@router.post(
    "/{session_id}/approve",
    response_model=SessionApprovalResponse,
    summary="Approve pending tool use",
    responses={
        400: {"model": ErrorResponse, "description": "No pending approval"},
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
)
async def approve_tool_use(
    session_id: str,
    approval: SessionApproval,
    manager: SessionManagerDep,
    approval_handler: ApprovalHandlerDep,
    _api_key: ApiKeyDep,
) -> SessionApprovalResponse:
    """Approve a pending tool use.

    Signals the waiting hook to proceed with the tool execution.
    The session transitions from WAITING_APPROVAL back to RUNNING.
    """
    try:
        await _process_approval_decision(
            session_id, approved=True, feedback=approval.feedback,
            manager=manager, approval_handler=approval_handler,
        )
        return SessionApprovalResponse(status="resumed")

    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SessionStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{session_id}/deny",
    response_model=SessionApprovalResponse,
    summary="Deny pending tool use",
    responses={
        400: {"model": ErrorResponse, "description": "No pending approval or missing feedback"},
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
)
async def deny_tool_use(
    session_id: str,
    denial: SessionApproval,
    manager: SessionManagerDep,
    approval_handler: ApprovalHandlerDep,
    _api_key: ApiKeyDep,
) -> SessionApprovalResponse:
    """Deny a pending tool use with required feedback.

    Signals the waiting hook to deny the tool execution with a reason.
    The feedback is passed back to Claude as the denial reason so it
    can adjust its approach.
    """
    try:
        feedback = denial.feedback or "User denied tool execution"
        await _process_approval_decision(
            session_id, approved=False, feedback=feedback,
            manager=manager, approval_handler=approval_handler,
        )
        return SessionApprovalResponse(status="denied")

    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SessionStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =============================================================================
# Session Cancellation
# =============================================================================


@router.post(
    "/{session_id}/cancel",
    response_model=SessionApprovalResponse,
    summary="Force-cancel a running session",
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
)
async def cancel_session(
    session_id: str,
    manager: SessionManagerDep,
    runtime: AgentRuntimeDep,
    approval_handler: ApprovalHandlerDep,
    _api_key: ApiKeyDep,
) -> SessionApprovalResponse:
    """Force-cancel a running or stuck session.

    This disconnects the SDK client, clears any pending approvals,
    and transitions the session to ERROR state. Use this when a
    session is stuck or you want to stop it immediately.
    """
    try:
        session = await manager.get_session(session_id)

        if session.status_enum in (SessionStatus.COMPLETED, SessionStatus.ERROR):
            return SessionApprovalResponse(status="already_terminal")

        # Clear pending approvals (unblocks any waiting hook with auto-deny)
        await approval_handler.clear_pending(session_id)

        # Disconnect the SDK client (kills the background stream)
        if runtime.is_session_active(session_id):
            await runtime.disconnect_session(session_id)

        # Force transition to error state
        try:
            await manager.fail_session(session_id, "Session cancelled by user")
        except SessionStateError:
            # Already in terminal state from disconnect cascade
            pass

        # Broadcast status change
        try:
            from src.api.websocket.session_stream import get_connection_manager
            ws_manager = get_connection_manager()
            await ws_manager.broadcast(session_id, {
                "type": "status",
                "status": "error",
                "session_id": session_id,
            })
        except Exception as e:
            logger.warning(f"Failed to broadcast cancel status: {e}")

        return SessionApprovalResponse(status="cancelled")

    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# =============================================================================
# SSE Streaming
# =============================================================================


@router.get(
    "/{session_id}/stream",
    summary="SSE stream for session messages",
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
)
async def stream_session_sse(
    session_id: str,
    manager: SessionManagerDep,
    runtime: AgentRuntimeDep,
    _api_key: ApiKeyDep,
) -> StreamingResponse:
    """Stream session messages via Server-Sent Events.

    Mobile fallback for clients that can't use WebSockets.
    """
    import json

    try:
        await manager.get_session(session_id)
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    async def event_generator():
        """Generate SSE events."""
        try:
            if runtime.is_session_active(session_id):
                async for message in runtime.stream_active_session(session_id):
                    message["timestamp"] = datetime.now(timezone.utc).isoformat()
                    yield f"data: {json.dumps(message)}\n\n"
            else:
                session = await manager.get_session(session_id)
                yield f"data: {json.dumps({'type': MessageType.STATUS.value, 'status': session.status})}\n\n"

        except Exception as e:
            logger.exception(f"SSE stream error for session {session_id}")
            yield f"data: {json.dumps({'type': MessageType.ERROR.value, 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
