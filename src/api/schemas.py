"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# Project Schemas
# =============================================================================


class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    name: str = Field(..., min_length=1, max_length=255)
    path: str = Field(..., min_length=1, max_length=1024)
    description: str | None = Field(None, max_length=500)
    default_allowed_tools: list[str] | None = None
    permission_mode: str = Field("default", pattern="^(default|acceptEdits|manual)$")
    auto_approve_patterns: list[str] | None = None
    validate_path: bool = True
    dev_command: str | None = None
    dev_port: int | None = None


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=500)
    default_allowed_tools: list[str] | None = None
    permission_mode: str | None = Field(None, pattern="^(default|acceptEdits|manual)$")
    auto_approve_patterns: list[str] | None = None
    dev_command: str | None = None
    dev_port: int | None = None


class ProjectResponse(BaseModel):
    """Schema for project responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    path: str
    description: str | None
    default_allowed_tools: list[str] | None
    permission_mode: str
    auto_approve_patterns: list[str] | None
    dev_command: str | None = None
    dev_port: int | None = None
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    """Schema for list of projects."""

    projects: list[ProjectResponse]
    total: int


class PreviewStatusResponse(BaseModel):
    """Schema for preview status responses."""

    running: bool
    url: str | None = None
    port: int | None = None
    pid: int | None = None
    uptime_seconds: int | None = None
    project_type: str | None = None
    error: str | None = None


# =============================================================================
# Session Schemas
# =============================================================================


class SessionCreate(BaseModel):
    """Schema for creating a new session."""

    project_id: str
    prompt: str = Field(..., min_length=1)
    name: str | None = Field(None, max_length=255)


class SessionResponse(BaseModel):
    """Schema for session responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    claude_session_id: str | None
    project_id: str
    name: str | None
    status: str
    last_prompt: str | None
    pending_approval: dict[str, Any] | None
    message_count: int
    total_cost_usd: float
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class SessionWithMessagesResponse(SessionResponse):
    """Schema for session with message history."""

    messages: list["MessageResponse"]


class SessionListResponse(BaseModel):
    """Schema for list of sessions."""

    sessions: list[SessionResponse]
    total: int


class SessionPrompt(BaseModel):
    """Schema for sending a prompt to a session."""

    prompt: str = Field(..., min_length=1)


class SessionApproval(BaseModel):
    """Schema for approving/denying tool use."""

    approved: bool = True
    feedback: str | None = None


class SessionApprovalResponse(BaseModel):
    """Schema for approval response."""

    status: str


# =============================================================================
# Message Schemas
# =============================================================================


class MessageResponse(BaseModel):
    """Schema for message responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    role: str
    content: str
    message_type: str | None
    metadata: dict[str, Any] | None = Field(None, alias="extra")
    timestamp: datetime


class MessageListResponse(BaseModel):
    """Schema for list of messages."""

    messages: list[MessageResponse]
    total: int


# =============================================================================
# Health Schemas
# =============================================================================


class HealthResponse(BaseModel):
    """Schema for health check response."""

    status: str
    version: str


class AgentHealthResponse(BaseModel):
    """Schema for agent health check response."""

    status: str
    cli_available: bool
    error: str | None = None


# =============================================================================
# WebSocket/SSE Schemas
# =============================================================================


class StreamMessage(BaseModel):
    """Schema for streaming messages (WebSocket/SSE)."""

    type: str
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_use_id: str | None = None
    tool_result: str | None = None
    is_error: bool | None = None
    session_id: str | None = None
    total_cost_usd: float | None = None
    duration_ms: int | None = None
    timestamp: datetime | None = None


# =============================================================================
# Error Schemas
# =============================================================================


class ErrorResponse(BaseModel):
    """Schema for error responses."""

    detail: str
    error_type: str | None = None


# =============================================================================
# External Session Schemas (Claude Code session discovery)
# =============================================================================


class ExternalSessionResponse(BaseModel):
    """Metadata for a Claude Code session discovered on the local filesystem."""

    session_id: str
    file_path: str
    file_size_bytes: int
    slug: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    model: str | None = None
    claude_code_version: str | None = None
    total_entries: int = 0
    user_messages: int = 0
    assistant_messages: int = 0
    has_subagents: bool = False
    cwd: str | None = None
    git_branch: str | None = None
    title: str | None = None


class ExternalSessionListResponse(BaseModel):
    """List of discovered external Claude Code sessions."""

    sessions: list[ExternalSessionResponse]
    total: int
    project_path: str
    claude_dir: str


class ExternalMessageResponse(BaseModel):
    """A single message parsed from a Claude Code JSONL session file."""

    id: str
    session_id: str
    role: str
    content: str
    message_type: str | None = None
    metadata: dict[str, Any] | None = None
    timestamp: str


class ExternalSessionDetailResponse(BaseModel):
    """Full conversation history for an external Claude Code session."""

    session_id: str
    slug: str | None = None
    model: str | None = None
    claude_code_version: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    messages: list[ExternalMessageResponse]
    total_messages: int


class ContinueExternalSessionRequest(BaseModel):
    """Request to continue an external session inside ZURK."""

    prompt: str = Field(..., min_length=1)
    name: str | None = None


# =============================================================================
# Global External Sessions (cross-project view)
# =============================================================================


class GlobalExternalSessionResponse(ExternalSessionResponse):
    """External session enriched with project context for the global view."""

    project_id: str
    project_name: str


class GlobalExternalSessionListResponse(BaseModel):
    """List of external sessions across all projects."""

    sessions: list[GlobalExternalSessionResponse]
    total: int


# =============================================================================
# Filesystem Browser (folder picker)
# =============================================================================


class DirectoryEntry(BaseModel):
    """A single directory entry for the folder picker."""

    name: str
    path: str
    has_children: bool = False
    project_indicators: list[str] = Field(default_factory=list)


class BreadcrumbEntry(BaseModel):
    """A single breadcrumb for folder navigation."""

    name: str
    path: str


class DirectoryListResponse(BaseModel):
    """Response for the filesystem browse endpoint."""

    current_path: str
    entries: list[DirectoryEntry]
    shortcuts: list[DirectoryEntry] = Field(default_factory=list)
    breadcrumbs: list[BreadcrumbEntry] = Field(default_factory=list)
    parent_path: str | None = None


# Update forward references
SessionWithMessagesResponse.model_rebuild()
