"""Constants used across ZURK core modules."""

from enum import Enum


# =============================================================================
# Message Types (from Claude Agent SDK)
# =============================================================================


class MessageType(str, Enum):
    """Types of messages from the Claude Agent SDK."""

    INIT = "init"
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    RESULT = "result"
    ERROR = "error"
    USER = "user"
    STATUS = "status"
    HISTORY = "history"
    PONG = "pong"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_PROCESSED = "approval_processed"


class MessageRole(str, Enum):
    """Roles for stored messages."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"


# Mapping from SDK message type to storage role
MESSAGE_TYPE_TO_ROLE: dict[str, str] = {
    MessageType.INIT.value: MessageRole.SYSTEM.value,
    MessageType.TEXT.value: MessageRole.ASSISTANT.value,
    MessageType.TOOL_USE.value: MessageRole.TOOL_USE.value,
    MessageType.TOOL_RESULT.value: MessageRole.TOOL_RESULT.value,
    MessageType.RESULT.value: MessageRole.SYSTEM.value,
    MessageType.USER.value: MessageRole.USER.value,
}


# =============================================================================
# Database field lengths
# =============================================================================

# Database field lengths
UUID_LENGTH = 36
NAME_MAX_LENGTH = 255
PATH_MAX_LENGTH = 1024
STATUS_MAX_LENGTH = 50
MESSAGE_TYPE_MAX_LENGTH = 100
CLAUDE_SESSION_ID_MAX_LENGTH = 255

# Content limits
LAST_PROMPT_MAX_LENGTH = 1000
DESCRIPTION_MAX_LENGTH = 500

# Default values for pagination
DEFAULT_LIST_LIMIT = 50
DEFAULT_LIST_OFFSET = 0

# Agent Runtime defaults
DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_PERMISSION_MODE = "default"

# Default allowed tools for sessions
DEFAULT_ALLOWED_TOOLS: tuple[str, ...] = (
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "WebSearch",
    "WebFetch",
)

# Valid permission modes (matches SDK PermissionMode)
VALID_PERMISSION_MODES: frozenset[str] = frozenset({
    "default",
    "acceptEdits",
    "plan",
    "bypassPermissions",
})
