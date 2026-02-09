"""Message transformation utilities for agent messages."""

from typing import Any

from src.core.constants import (
    MessageType,
    MessageRole,
    MESSAGE_TYPE_TO_ROLE,
)


class MessageMapper:
    """Maps agent SDK messages to storage format.

    This class handles the transformation between the raw message format
    from the Claude Agent SDK and the format we store in our database.
    """

    @staticmethod
    def get_role(msg_type: str) -> str | None:
        """Map message type to storage role.

        Args:
            msg_type: The message type from SDK (e.g., "text", "tool_use")

        Returns:
            The role for storage, or None if type shouldn't be stored
        """
        return MESSAGE_TYPE_TO_ROLE.get(msg_type)

    @staticmethod
    def get_content(message: dict[str, Any]) -> str | None:
        """Extract displayable content from a message.

        Args:
            message: The raw message dict from the SDK

        Returns:
            Human-readable content string, or None if no content
        """
        msg_type = message.get("type", "")

        if msg_type == MessageType.TEXT.value:
            return message.get("content", "")

        elif msg_type == MessageType.TOOL_USE.value:
            tool_name = message.get("tool_name", "unknown")
            return f"Tool: {tool_name}"

        elif msg_type == MessageType.TOOL_RESULT.value:
            return message.get("tool_result", "")

        elif msg_type == MessageType.INIT.value:
            session_id = message.get("session_id", "")
            return f"Session started: {session_id}"

        elif msg_type == MessageType.RESULT.value:
            cost = message.get("total_cost_usd", 0)
            return f"Session completed. Cost: ${cost:.4f}"

        elif msg_type == MessageType.ERROR.value:
            return message.get("content", "Unknown error")

        return None

    @staticmethod
    def is_completion_message(message: dict[str, Any]) -> bool:
        """Check if this message indicates session completion.

        Args:
            message: The raw message dict

        Returns:
            True if this is a completion message
        """
        return message.get("type") == MessageType.RESULT.value

    @staticmethod
    def is_successful_completion(message: dict[str, Any]) -> bool:
        """Check if this message indicates successful completion.

        Args:
            message: The raw message dict (must be a result message)

        Returns:
            True if session completed successfully
        """
        return (
            message.get("type") == MessageType.RESULT.value
            and message.get("is_complete", False)
        )

    @staticmethod
    def get_session_id_from_init(message: dict[str, Any]) -> str | None:
        """Extract Claude session ID from init message.

        Args:
            message: The raw message dict

        Returns:
            The Claude session ID, or None if not an init message
        """
        if message.get("type") == MessageType.INIT.value:
            return message.get("session_id")
        return None

    @staticmethod
    def get_cost(message: dict[str, Any]) -> float:
        """Extract cost from a result message.

        Args:
            message: The raw message dict

        Returns:
            The cost in USD, or 0 if not available
        """
        return message.get("total_cost_usd", 0.0)

    @staticmethod
    def get_error_message(message: dict[str, Any]) -> str:
        """Extract error message from a failed result.

        Args:
            message: The raw message dict

        Returns:
            Error message string
        """
        return message.get("content", "Session ended with error")
