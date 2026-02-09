"""Shared exceptions for ZURK core business logic."""


class ZurkError(Exception):
    """Base exception for all ZURK errors."""


# Project-related exceptions
class ProjectNotFoundError(ZurkError):
    """Raised when a project is not found."""


class ProjectPathExistsError(ZurkError):
    """Raised when attempting to register a project with an existing path."""


class ProjectPathInvalidError(ZurkError):
    """Raised when a project path is invalid."""


class ProjectValidationError(ZurkError):
    """Raised when project data fails validation."""


# Session-related exceptions
class SessionNotFoundError(ZurkError):
    """Raised when a session is not found."""


class SessionStateError(ZurkError):
    """Raised when an invalid state transition is attempted."""


# Agent Runtime exceptions
class AgentRuntimeError(ZurkError):
    """Base exception for agent runtime errors."""


class AgentSessionError(AgentRuntimeError):
    """Raised when there's an error with an agent session."""


class AgentConnectionError(AgentRuntimeError):
    """Raised when the SDK connection fails."""


class AgentNotConnectedError(AgentRuntimeError):
    """Raised when trying to use an agent that isn't connected."""
