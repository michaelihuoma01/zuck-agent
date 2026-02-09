"""Type definitions for ZURK core modules."""

from typing import Any, Literal, TypedDict


RiskLevel = Literal["low", "medium", "high"]
DiffTier = Literal["inline", "truncated"]


class DiffStats(TypedDict):
    """Addition/deletion counts from a diff."""

    additions: int
    deletions: int


class PendingApproval(TypedDict, total=False):
    """Structure for pending tool approval data.

    Stored in Session.pending_approval JSON field when a tool
    requires user approval before execution.
    """

    tool_name: str  # Required: e.g., "Write", "Bash", "Edit"
    tool_input: dict[str, Any]  # Required: Input parameters to the tool
    tool_use_id: str  # Required: SDK's tool use ID for response
    file_path: str | None  # Optional: Target path for file operations
    diff: str | None  # Optional: Unified diff or command string
    diff_stats: DiffStats | None  # Optional: addition/deletion counts
    risk_level: RiskLevel | None  # Optional: "low", "medium", "high"
    diff_tier: DiffTier  # "inline" (full diff) or "truncated" (head+tail preview)
    total_bytes: int  # Full diff size in bytes (before any truncation)
    total_lines: int  # Total lines in full diff (before any truncation)
    requested_at: str  # ISO format timestamp when approval was requested


class MessageExtra(TypedDict, total=False):
    """Structure for message extra/metadata field.

    Stored in Message.extra JSON field for additional context.
    """

    tokens: int  # Token count for this message
    input_tokens: int  # Input tokens used
    output_tokens: int  # Output tokens generated
    cost_usd: float  # Cost for this specific message
    tool_use_id: str  # ID if this is a tool_use/tool_result message
    tool_name: str  # Tool name if applicable
    timing_ms: int  # How long the operation took


class AgentMessage(TypedDict, total=False):
    """Unified message format from AgentRuntime for streaming.

    This provides a consistent interface for API consumers,
    hiding SDK-specific message type details.
    """

    # Message identification
    type: str  # "init", "text", "tool_use", "tool_result", "result", "error"
    session_id: str  # Claude's session ID (present in init message)

    # Content fields (vary by type)
    content: str  # Text content for text/error messages
    tool_name: str  # Tool name for tool_use/tool_result
    tool_input: dict[str, Any]  # Tool input parameters
    tool_use_id: str  # SDK's tool use ID
    tool_result: str  # Tool execution result
    is_error: bool  # Whether tool result is an error

    # Result fields (present in "result" type)
    total_cost_usd: float  # Total API cost
    duration_ms: int  # Total duration
    num_turns: int  # Number of conversation turns
    is_complete: bool  # Whether session completed successfully

    # Metadata
    model: str  # Model used (e.g., "claude-sonnet-4-5")
    raw_type: str  # Original SDK message type for debugging
