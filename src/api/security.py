"""API security: authentication, authorization, and rate limiting."""

import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status, Request, WebSocket
from fastapi.security import APIKeyHeader

from src.config import Settings, get_settings


# API Key header scheme
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


class AuthenticationError(HTTPException):
    """Raised when authentication fails."""

    def __init__(self, detail: str = "Invalid or missing API key"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "API-Key"},
        )


def _constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks."""
    return secrets.compare_digest(a.encode(), b.encode())


async def verify_api_key(
    api_key: str | None = Depends(API_KEY_HEADER),
    settings: Settings = Depends(get_settings),
) -> str:
    """Verify API key from X-API-Key header.

    Args:
        api_key: The API key from the request header
        settings: Application settings

    Returns:
        The verified API key

    Raises:
        AuthenticationError: If API key is missing or invalid
    """
    # If no API key configured in settings, auth is disabled (dev mode)
    if not settings.api_key:
        return "dev-mode"

    if not api_key:
        raise AuthenticationError("Missing API key. Include X-API-Key header.")

    if not _constant_time_compare(api_key, settings.api_key):
        raise AuthenticationError("Invalid API key")

    return api_key


async def verify_websocket_api_key(
    websocket: WebSocket,
    settings: Settings = Depends(get_settings),
) -> str:
    """Verify API key for WebSocket connections.

    WebSocket auth can come from:
    1. Query parameter: ?api_key=xxx
    2. Header: X-API-Key (during handshake)

    Args:
        websocket: The WebSocket connection
        settings: Application settings

    Returns:
        The verified API key

    Raises:
        Will close WebSocket with 4001 if auth fails
    """
    # If no API key configured, auth is disabled
    if not settings.api_key:
        return "dev-mode"

    # Try query parameter first
    api_key = websocket.query_params.get("api_key")

    # Fall back to header
    if not api_key:
        api_key = websocket.headers.get("x-api-key")

    if not api_key:
        await websocket.close(code=4001, reason="Missing API key")
        raise AuthenticationError("Missing API key")

    if not _constant_time_compare(api_key, settings.api_key):
        await websocket.close(code=4001, reason="Invalid API key")
        raise AuthenticationError("Invalid API key")

    return api_key


def generate_api_key() -> str:
    """Generate a secure random API key.

    Returns:
        A 32-character hex string (128 bits of entropy)
    """
    return secrets.token_hex(16)


# Type alias for dependency injection
ApiKeyDep = Annotated[str, Depends(verify_api_key)]
WebSocketApiKeyDep = Annotated[str, Depends(verify_websocket_api_key)]


# Optional auth - doesn't raise, just returns None if no key
async def optional_api_key(
    api_key: str | None = Depends(API_KEY_HEADER),
    settings: Settings = Depends(get_settings),
) -> str | None:
    """Optionally verify API key - returns None if not provided or invalid.

    Use this for endpoints that should work without auth but may have
    enhanced functionality with auth.
    """
    if not settings.api_key:
        return "dev-mode"

    if not api_key:
        return None

    if _constant_time_compare(api_key, settings.api_key):
        return api_key

    return None


OptionalApiKeyDep = Annotated[str | None, Depends(optional_api_key)]
