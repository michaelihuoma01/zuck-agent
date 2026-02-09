"""Read and parse Claude Code JSONL session files into ZURK-compatible messages.

Claude Code stores session transcripts as JSONL files where each line is a JSON
object with a ``type`` field. This module parses those files into dicts that
match the frontend ``Message`` interface so they can be rendered by the existing
``MessageList`` / ``MessageBubble`` components.

JSONL entry types we care about:

* ``user``      – user prompts (content is string or content-block array)
* ``assistant`` – Claude responses (message.content is array of text / tool_use blocks)

Everything else (``progress``, ``system``, ``file-history-snapshot``, ``result``)
is skipped.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SessionMeta:
    """Metadata extracted from the first/last JSONL entries."""

    session_id: str
    slug: str | None = None
    model: str | None = None
    claude_code_version: str | None = None
    started_at: str | None = None
    ended_at: str | None = None


@dataclass
class ParsedMessage:
    """A single message suitable for the frontend ``Message`` interface."""

    id: str
    session_id: str
    role: str
    content: str
    message_type: str | None = None
    metadata: dict | None = None
    timestamp: str = ""


# Entry types that produce displayable messages
_DISPLAYABLE_TYPES = frozenset({"user", "assistant"})


def read_session_messages(file_path: str | Path) -> tuple[SessionMeta, list[ParsedMessage]]:
    """Parse a JSONL session file into metadata + ordered messages.

    Args:
        file_path: Absolute path to the ``.jsonl`` file.

    Returns:
        A tuple of ``(SessionMeta, list[ParsedMessage])``.

    Raises:
        FileNotFoundError: If the file does not exist.
        OSError: On other I/O errors.
    """
    path = Path(file_path)
    messages: list[ParsedMessage] = []
    meta = SessionMeta(session_id=path.stem)

    first_entry: dict | None = None
    last_timestamp: str | None = None

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line_no, raw_line in enumerate(f, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue

            try:
                entry = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                logger.debug("Skipping malformed JSON at %s:%d", path.name, line_no)
                continue

            # Capture first entry for metadata
            if first_entry is None:
                first_entry = entry

            # Track last timestamp for ended_at
            ts = entry.get("timestamp")
            if ts:
                last_timestamp = ts

            entry_type = entry.get("type")
            if entry_type not in _DISPLAYABLE_TYPES:
                continue

            entry_uuid = entry.get("uuid", f"line-{line_no}")
            session_id = entry.get("sessionId", meta.session_id)
            timestamp = ts or ""

            if entry_type == "user":
                msgs = _parse_user_entry(entry, entry_uuid, session_id, timestamp)
            elif entry_type == "assistant":
                msgs = _parse_assistant_entry(entry, entry_uuid, session_id, timestamp)
            else:
                continue

            messages.extend(msgs)

    # Populate metadata from first entry
    if first_entry:
        meta.session_id = first_entry.get("sessionId", meta.session_id)
        meta.slug = first_entry.get("slug")
        meta.claude_code_version = first_entry.get("version")
        meta.started_at = first_entry.get("timestamp")

    meta.ended_at = last_timestamp

    # Find model from first assistant entry that has one
    if not meta.model:
        for msg in messages:
            if msg.role == "assistant" and msg.metadata and msg.metadata.get("model"):
                meta.model = msg.metadata["model"]
                break

    return meta, messages


def _parse_user_entry(
    entry: dict,
    entry_uuid: str,
    session_id: str,
    timestamp: str,
) -> list[ParsedMessage]:
    """Parse a ``type: "user"`` JSONL entry.

    User entries can have:
    - ``message.content`` as a plain string (simple prompt)
    - ``message.content`` as a list of content blocks (tool_result, text, etc.)
    """
    message = entry.get("message", {})
    content = message.get("content", "")

    # Simple string content → single user message
    if isinstance(content, str):
        return [
            ParsedMessage(
                id=entry_uuid,
                session_id=session_id,
                role="user",
                content=content,
                message_type="user",
                timestamp=timestamp,
            )
        ]

    # Array of content blocks (tool_result responses, etc.)
    msgs: list[ParsedMessage] = []
    if isinstance(content, list):
        for i, block in enumerate(content):
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            block_id = f"{entry_uuid}-{i}" if len(content) > 1 else entry_uuid

            if block_type == "tool_result":
                # Tool result from user turn
                result_content = block.get("content", "")
                if isinstance(result_content, list):
                    # content can be [{type:"text", text:"..."}]
                    parts = []
                    for part in result_content:
                        if isinstance(part, dict) and part.get("text"):
                            parts.append(part["text"])
                    result_content = "\n".join(parts) if parts else str(result_content)
                msgs.append(
                    ParsedMessage(
                        id=block_id,
                        session_id=session_id,
                        role="tool_result",
                        content=str(result_content),
                        message_type="tool_result",
                        metadata={
                            "tool_use_id": block.get("tool_use_id"),
                            "is_error": block.get("is_error", False),
                        },
                        timestamp=timestamp,
                    )
                )
            elif block_type == "text":
                msgs.append(
                    ParsedMessage(
                        id=block_id,
                        session_id=session_id,
                        role="user",
                        content=block.get("text", ""),
                        message_type="user",
                        timestamp=timestamp,
                    )
                )

    return msgs


def _parse_assistant_entry(
    entry: dict,
    entry_uuid: str,
    session_id: str,
    timestamp: str,
) -> list[ParsedMessage]:
    """Parse a ``type: "assistant"`` JSONL entry.

    Assistant entries have ``message.content`` as an array of blocks:
    - ``{type: "text", text: "..."}`` → assistant text message
    - ``{type: "tool_use", id: "...", name: "...", input: {...}}`` → tool_use message
    """
    message = entry.get("message", {})
    content_blocks = message.get("content", [])
    model = message.get("model")

    if not isinstance(content_blocks, list):
        return []

    msgs: list[ParsedMessage] = []
    for i, block in enumerate(content_blocks):
        if not isinstance(block, dict):
            continue

        block_type = block.get("type", "")
        block_id = f"{entry_uuid}-{i}" if len(content_blocks) > 1 else entry_uuid

        if block_type == "text":
            text = block.get("text", "")
            if not text:
                continue
            msgs.append(
                ParsedMessage(
                    id=block_id,
                    session_id=session_id,
                    role="assistant",
                    content=text,
                    message_type="text",
                    metadata={"model": model} if model else None,
                    timestamp=timestamp,
                )
            )
        elif block_type == "tool_use":
            tool_name = block.get("name", "unknown")
            tool_input = block.get("input", {})
            msgs.append(
                ParsedMessage(
                    id=block_id,
                    session_id=session_id,
                    role="tool_use",
                    content=f"Tool: {tool_name}",
                    message_type="tool_use",
                    metadata={
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                        "tool_use_id": block.get("id"),
                        "model": model,
                    },
                    timestamp=timestamp,
                )
            )

    return msgs
