"""Discover external Claude Code sessions from the local filesystem.

Claude Code stores session transcripts as JSONL files at:
    ~/.claude/projects/<encoded-path>/<session-id>.jsonl

where <encoded-path> replaces '/' with '-' in the project's absolute path.
This module scans those files to surface sessions started outside of ZURK
(e.g., from VS Code or the CLI).
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Claude Code stores sessions under this base directory
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

# How many bytes to read from the end of a file to find the last entry
TAIL_READ_BYTES = 8192

# Max JSONL files to scan per project (safety limit)
MAX_FILES_PER_PROJECT = 100

# How many JSONL lines to scan for metadata fields (slug, cwd, gitBranch)
# These fields may not appear on line 1 when the first entry is a file-history-snapshot
METADATA_SCAN_LINES = 10


@dataclass
class ExternalSession:
    """Metadata extracted from a Claude Code JSONL session file."""

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
    extra: dict = field(default_factory=dict)


def encode_project_path(project_path: str) -> str:
    """Convert an absolute path to Claude Code's encoded directory name.

    '/Users/mike/Documents/zuck' → '-Users-mike-Documents-zuck'
    """
    # Normalize: resolve symlinks, remove trailing slashes
    normalized = os.path.normpath(project_path)
    # Replace '/' with '-'
    return normalized.replace("/", "-")


def _parse_first_line(line: str) -> dict:
    """Parse the first JSONL entry for session metadata."""
    try:
        return json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return {}


def _parse_last_lines(data: bytes) -> dict:
    """Parse the last complete JSONL entry from a tail read."""
    try:
        text = data.decode("utf-8", errors="replace")
        # Split by newline, filter empties, take last non-empty line
        lines = [l for l in text.strip().split("\n") if l.strip()]
        if not lines:
            return {}
        return json.loads(lines[-1])
    except (json.JSONDecodeError, ValueError):
        return {}


def _count_entries(file_path: Path) -> tuple[int, int, int]:
    """Count total entries, user messages, and assistant messages.

    Uses a streaming approach to avoid loading the full file into memory.
    Returns (total, user_count, assistant_count).
    """
    total = 0
    user_count = 0
    assistant_count = 0

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                total += 1
                # Quick check without full JSON parse
                if '"type":"user"' in line or '"type": "user"' in line:
                    user_count += 1
                elif '"type":"assistant"' in line or '"type": "assistant"' in line:
                    assistant_count += 1
    except OSError:
        pass

    return total, user_count, assistant_count


def _find_model(file_path: Path) -> str | None:
    """Find the model name from the first assistant entry.

    Scans line by line until we find an assistant message with a model field.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"type":"assistant"' not in line and '"type": "assistant"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                    model = entry.get("message", {}).get("model")
                    if model:
                        return model
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError:
        pass
    return None


def _parse_metadata_fields(file_path: Path) -> dict:
    """Scan the first METADATA_SCAN_LINES lines for slug, cwd, and gitBranch.

    These fields can appear on any early JSONL line — not necessarily line 1.
    Returns a dict with keys 'slug', 'cwd', 'gitBranch' (present only if found).
    """
    result: dict = {}
    target_keys = {"slug", "cwd", "gitBranch"}
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= METADATA_SCAN_LINES:
                    break
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                for key in target_keys:
                    if key not in result and key in entry:
                        result[key] = entry[key]
                if target_keys <= result.keys():
                    break  # Found all target keys
    except OSError:
        pass
    return result


def _extract_first_user_message(file_path: Path, max_lines: int = 50) -> str | None:
    """Extract the text of the first user message for use as a session title.

    Scans up to max_lines to find the first ``type: "user"`` entry and
    extracts the message content string (or the first text block if content
    is a list).  Returns the raw text (callers truncate for display).
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                if '"type":"user"' not in line and '"type": "user"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if entry.get("type") != "user":
                    continue
                msg = entry.get("message", {})
                # message.content can be a plain string…
                if isinstance(msg, dict):
                    content = msg.get("content", "")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
                    # …or a list of content blocks (text, image, etc.)
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "").strip()
                                if text:
                                    return text
                # Older format: message is a plain string
                if isinstance(msg, str) and msg.strip():
                    return msg.strip()
    except OSError:
        pass
    return None


def discover_session(file_path: Path) -> ExternalSession | None:
    """Extract metadata from a single JSONL session file.

    Returns None if the file can't be parsed or is empty.
    """
    try:
        stat = file_path.stat()
        if stat.st_size == 0:
            return None

        session_id = file_path.stem  # UUID from filename

        # Read first line for start metadata
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline()

        first = _parse_first_line(first_line)
        if not first:
            return None

        # Scan early lines for metadata (slug, cwd, gitBranch)
        meta = _parse_metadata_fields(file_path)

        # Read last entry for end timestamp
        with open(file_path, "rb") as f:
            # Seek to near end of file
            seek_pos = max(0, stat.st_size - TAIL_READ_BYTES)
            f.seek(seek_pos)
            tail_data = f.read()
        last = _parse_last_lines(tail_data)

        # Count entries (streaming, memory-efficient)
        total, user_count, assistant_count = _count_entries(file_path)

        # Find model from first assistant message
        model = _find_model(file_path)

        # Extract first user message as title
        title = _extract_first_user_message(file_path)

        # Check for subagent directories
        subagent_dir = file_path.parent / session_id / "subagents"
        has_subagents = subagent_dir.is_dir() and any(subagent_dir.iterdir())

        return ExternalSession(
            session_id=first.get("sessionId", session_id),
            file_path=str(file_path),
            file_size_bytes=stat.st_size,
            slug=meta.get("slug") or first.get("slug"),
            started_at=first.get("timestamp"),
            ended_at=last.get("timestamp"),
            model=model,
            claude_code_version=first.get("version"),
            total_entries=total,
            user_messages=user_count,
            assistant_messages=assistant_count,
            has_subagents=has_subagents,
            cwd=meta.get("cwd"),
            git_branch=meta.get("gitBranch"),
            title=title,
        )

    except OSError as e:
        logger.warning(f"Failed to read session file {file_path}: {e}")
        return None


def discover_sessions(project_path: str) -> list[ExternalSession]:
    """Discover all Claude Code sessions for a given project path.

    Args:
        project_path: Absolute path to the project directory.

    Returns:
        List of ExternalSession objects sorted by started_at (newest first).
    """
    encoded = encode_project_path(project_path)
    sessions_dir = CLAUDE_PROJECTS_DIR / encoded

    if not sessions_dir.is_dir():
        logger.debug(f"No Claude sessions directory found at {sessions_dir}")
        return []

    # Find all top-level JSONL files (session transcripts)
    jsonl_files = sorted(
        sessions_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:MAX_FILES_PER_PROJECT]

    sessions: list[ExternalSession] = []
    for file_path in jsonl_files:
        session = discover_session(file_path)
        if session:
            sessions.append(session)

    # Sort by started_at descending (newest first)
    sessions.sort(
        key=lambda s: s.started_at or "",
        reverse=True,
    )

    return sessions
