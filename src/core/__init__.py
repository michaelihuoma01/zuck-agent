"""Core business logic for ZURK."""

from src.core.exceptions import (
    ZurkError,
    ProjectNotFoundError,
    ProjectPathExistsError,
    ProjectPathInvalidError,
    ProjectValidationError,
    SessionNotFoundError,
    SessionStateError,
)
from src.core.project_registry import ProjectRegistry, VALID_PERMISSION_MODES
from src.core.session_manager import SessionManager, VALID_TRANSITIONS
from src.core.constants import (
    UUID_LENGTH,
    NAME_MAX_LENGTH,
    PATH_MAX_LENGTH,
    STATUS_MAX_LENGTH,
    MESSAGE_TYPE_MAX_LENGTH,
    CLAUDE_SESSION_ID_MAX_LENGTH,
    LAST_PROMPT_MAX_LENGTH,
    DESCRIPTION_MAX_LENGTH,
    DEFAULT_LIST_LIMIT,
    DEFAULT_LIST_OFFSET,
)
from src.core.types import PendingApproval, MessageExtra

__all__ = [
    # Base exception
    "ZurkError",
    # Project exceptions
    "ProjectNotFoundError",
    "ProjectPathExistsError",
    "ProjectPathInvalidError",
    "ProjectValidationError",
    # Session exceptions
    "SessionNotFoundError",
    "SessionStateError",
    # Project Registry
    "ProjectRegistry",
    "VALID_PERMISSION_MODES",
    # Session Manager
    "SessionManager",
    "VALID_TRANSITIONS",
    # Constants
    "UUID_LENGTH",
    "NAME_MAX_LENGTH",
    "PATH_MAX_LENGTH",
    "STATUS_MAX_LENGTH",
    "MESSAGE_TYPE_MAX_LENGTH",
    "CLAUDE_SESSION_ID_MAX_LENGTH",
    "LAST_PROMPT_MAX_LENGTH",
    "DESCRIPTION_MAX_LENGTH",
    "DEFAULT_LIST_LIMIT",
    "DEFAULT_LIST_OFFSET",
    # Types
    "PendingApproval",
    "MessageExtra",
]
