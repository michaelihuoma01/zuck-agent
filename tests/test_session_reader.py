"""Tests for the session reader utility that parses Claude Code JSONL files."""

import json
import tempfile
from pathlib import Path

import pytest

from src.utils.session_reader import read_session_messages, ParsedMessage, SessionMeta


def _write_jsonl(lines: list[dict]) -> str:
    """Write a list of dicts as a JSONL temp file, returning the path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    for line in lines:
        f.write(json.dumps(line) + "\n")
    f.close()
    return f.name


# ── Metadata extraction ──────────────────────────────────────────────


class TestSessionMeta:
    """Tests for metadata extraction from JSONL files."""

    def test_extracts_metadata_from_first_entry(self):
        path = _write_jsonl([
            {
                "type": "user",
                "sessionId": "ses-123",
                "slug": "fix-auth-bug",
                "version": "1.2.3",
                "timestamp": "2025-01-01T10:00:00Z",
                "message": {"content": "Hello"},
            },
        ])
        meta, _ = read_session_messages(path)

        assert meta.session_id == "ses-123"
        assert meta.slug == "fix-auth-bug"
        assert meta.claude_code_version == "1.2.3"
        assert meta.started_at == "2025-01-01T10:00:00Z"

    def test_ended_at_from_last_timestamp(self):
        path = _write_jsonl([
            {
                "type": "user",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:00:00Z",
                "message": {"content": "Hello"},
            },
            {
                "type": "assistant",
                "timestamp": "2025-01-01T10:05:00Z",
                "message": {"content": [{"type": "text", "text": "Hi"}]},
            },
        ])
        meta, _ = read_session_messages(path)

        assert meta.ended_at == "2025-01-01T10:05:00Z"

    def test_model_extracted_from_first_assistant(self):
        path = _write_jsonl([
            {
                "type": "user",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:00:00Z",
                "message": {"content": "Hello"},
            },
            {
                "type": "assistant",
                "timestamp": "2025-01-01T10:01:00Z",
                "message": {
                    "model": "claude-opus-4-6",
                    "content": [{"type": "text", "text": "Hello"}],
                },
            },
        ])
        meta, _ = read_session_messages(path)

        assert meta.model == "claude-opus-4-6"

    def test_falls_back_to_filename_stem_for_session_id(self):
        """When sessionId is absent, use the file stem."""
        path = _write_jsonl([
            {
                "type": "user",
                "timestamp": "2025-01-01T10:00:00Z",
                "message": {"content": "Hi"},
            },
        ])
        meta, _ = read_session_messages(path)

        # session_id should be the temp file stem
        assert meta.session_id == Path(path).stem


# ── User message parsing ─────────────────────────────────────────────


class TestUserMessages:
    """Tests for parsing 'type: user' entries."""

    def test_simple_string_content(self):
        path = _write_jsonl([
            {
                "type": "user",
                "uuid": "u1",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:00:00Z",
                "message": {"content": "Fix the login bug"},
            },
        ])
        _, msgs = read_session_messages(path)

        assert len(msgs) == 1
        assert msgs[0].role == "user"
        assert msgs[0].content == "Fix the login bug"
        assert msgs[0].message_type == "user"
        assert msgs[0].id == "u1"

    def test_tool_result_content_blocks(self):
        """User entries with content blocks containing tool_result."""
        path = _write_jsonl([
            {
                "type": "user",
                "uuid": "u2",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:01:00Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-abc",
                            "content": "File written successfully",
                            "is_error": False,
                        },
                    ],
                },
            },
        ])
        _, msgs = read_session_messages(path)

        assert len(msgs) == 1
        assert msgs[0].role == "tool_result"
        assert msgs[0].content == "File written successfully"
        assert msgs[0].message_type == "tool_result"
        assert msgs[0].metadata["tool_use_id"] == "tool-abc"
        assert msgs[0].metadata["is_error"] is False

    def test_tool_result_with_nested_text_content(self):
        """Tool results where content is a list of text blocks."""
        path = _write_jsonl([
            {
                "type": "user",
                "uuid": "u3",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:02:00Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-xyz",
                            "content": [
                                {"type": "text", "text": "line 1"},
                                {"type": "text", "text": "line 2"},
                            ],
                        },
                    ],
                },
            },
        ])
        _, msgs = read_session_messages(path)

        assert len(msgs) == 1
        assert msgs[0].content == "line 1\nline 2"

    def test_multiple_content_blocks_get_suffixed_ids(self):
        """Multiple blocks in one entry get -0, -1 suffixes."""
        path = _write_jsonl([
            {
                "type": "user",
                "uuid": "u4",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:03:00Z",
                "message": {
                    "content": [
                        {"type": "text", "text": "Some context"},
                        {
                            "type": "tool_result",
                            "tool_use_id": "t1",
                            "content": "Result",
                        },
                    ],
                },
            },
        ])
        _, msgs = read_session_messages(path)

        assert len(msgs) == 2
        assert msgs[0].id == "u4-0"
        assert msgs[1].id == "u4-1"


# ── Assistant message parsing ────────────────────────────────────────


class TestAssistantMessages:
    """Tests for parsing 'type: assistant' entries."""

    def test_single_text_block(self):
        path = _write_jsonl([
            {
                "type": "assistant",
                "uuid": "a1",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:01:00Z",
                "message": {
                    "model": "claude-sonnet-4-5",
                    "content": [{"type": "text", "text": "Here is the fix..."}],
                },
            },
        ])
        _, msgs = read_session_messages(path)

        assert len(msgs) == 1
        assert msgs[0].role == "assistant"
        assert msgs[0].content == "Here is the fix..."
        assert msgs[0].message_type == "text"
        assert msgs[0].metadata["model"] == "claude-sonnet-4-5"

    def test_tool_use_block(self):
        path = _write_jsonl([
            {
                "type": "assistant",
                "uuid": "a2",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:02:00Z",
                "message": {
                    "model": "claude-sonnet-4-5",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tu-1",
                            "name": "Edit",
                            "input": {"file": "main.py", "old": "a", "new": "b"},
                        },
                    ],
                },
            },
        ])
        _, msgs = read_session_messages(path)

        assert len(msgs) == 1
        assert msgs[0].role == "tool_use"
        assert msgs[0].content == "Tool: Edit"
        assert msgs[0].message_type == "tool_use"
        assert msgs[0].metadata["tool_name"] == "Edit"
        assert msgs[0].metadata["tool_input"]["file"] == "main.py"
        assert msgs[0].metadata["tool_use_id"] == "tu-1"

    def test_mixed_text_and_tool_use_blocks(self):
        """Assistant entry with both text and tool_use blocks."""
        path = _write_jsonl([
            {
                "type": "assistant",
                "uuid": "a3",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:03:00Z",
                "message": {
                    "content": [
                        {"type": "text", "text": "Let me edit the file."},
                        {
                            "type": "tool_use",
                            "id": "tu-2",
                            "name": "Write",
                            "input": {"path": "foo.txt"},
                        },
                    ],
                },
            },
        ])
        _, msgs = read_session_messages(path)

        assert len(msgs) == 2
        assert msgs[0].role == "assistant"
        assert msgs[0].id == "a3-0"
        assert msgs[1].role == "tool_use"
        assert msgs[1].id == "a3-1"

    def test_empty_text_block_skipped(self):
        """Text blocks with empty string are filtered out."""
        path = _write_jsonl([
            {
                "type": "assistant",
                "uuid": "a4",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:04:00Z",
                "message": {
                    "content": [
                        {"type": "text", "text": ""},
                        {"type": "text", "text": "Actual content"},
                    ],
                },
            },
        ])
        _, msgs = read_session_messages(path)

        assert len(msgs) == 1
        assert msgs[0].content == "Actual content"


# ── Skipped entry types ──────────────────────────────────────────────


class TestSkippedEntries:
    """Tests that non-displayable entry types are ignored."""

    def test_progress_entries_skipped(self):
        path = _write_jsonl([
            {
                "type": "user",
                "uuid": "u1",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:00:00Z",
                "message": {"content": "Hello"},
            },
            {
                "type": "progress",
                "uuid": "p1",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:00:01Z",
            },
            {
                "type": "system",
                "uuid": "s1",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:00:02Z",
            },
            {
                "type": "result",
                "uuid": "r1",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:00:03Z",
            },
        ])
        _, msgs = read_session_messages(path)

        assert len(msgs) == 1
        assert msgs[0].role == "user"

    def test_file_history_snapshot_skipped(self):
        path = _write_jsonl([
            {
                "type": "file-history-snapshot",
                "uuid": "fhs-1",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:00:00Z",
            },
            {
                "type": "user",
                "uuid": "u1",
                "sessionId": "ses-1",
                "timestamp": "2025-01-01T10:00:01Z",
                "message": {"content": "Hello"},
            },
        ])
        _, msgs = read_session_messages(path)

        assert len(msgs) == 1


# ── Edge cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_file(self):
        path = _write_jsonl([])
        meta, msgs = read_session_messages(path)

        assert msgs == []
        # session_id falls back to file stem
        assert meta.session_id == Path(path).stem

    def test_malformed_json_lines_skipped(self):
        """Malformed lines are skipped, valid lines are still parsed."""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
        f.write('{"type":"user","uuid":"u1","sessionId":"ses-1","timestamp":"T","message":{"content":"Good"}}\n')
        f.write("this is not json\n")
        f.write('{"type":"assistant","uuid":"a1","sessionId":"ses-1","timestamp":"T","message":{"content":[{"type":"text","text":"Also good"}]}}\n')
        f.close()

        _, msgs = read_session_messages(f.name)

        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[1].role == "assistant"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            read_session_messages("/nonexistent/path/abc123.jsonl")

    def test_assistant_with_non_list_content(self):
        """If assistant content is not a list, produce no messages."""
        path = _write_jsonl([
            {
                "type": "assistant",
                "uuid": "a1",
                "sessionId": "ses-1",
                "timestamp": "T",
                "message": {"content": "just a string"},
            },
        ])
        _, msgs = read_session_messages(path)

        assert msgs == []

    def test_single_block_gets_no_suffix(self):
        """Single-block entries use the raw uuid without -0 suffix."""
        path = _write_jsonl([
            {
                "type": "assistant",
                "uuid": "a1",
                "sessionId": "ses-1",
                "timestamp": "T",
                "message": {
                    "content": [{"type": "text", "text": "Hi"}],
                },
            },
        ])
        _, msgs = read_session_messages(path)

        assert msgs[0].id == "a1"


# ── Full conversation flow ───────────────────────────────────────────


class TestFullConversation:
    """End-to-end test with a realistic multi-turn conversation."""

    def test_realistic_session(self):
        path = _write_jsonl([
            {
                "type": "user",
                "uuid": "u1",
                "sessionId": "ses-abc",
                "slug": "implement-auth",
                "version": "1.5.0",
                "timestamp": "2025-06-01T09:00:00Z",
                "message": {"content": "Add JWT authentication"},
            },
            {
                "type": "assistant",
                "uuid": "a1",
                "sessionId": "ses-abc",
                "timestamp": "2025-06-01T09:00:05Z",
                "message": {
                    "model": "claude-opus-4-6",
                    "content": [
                        {"type": "text", "text": "I'll add JWT auth. Let me read the current code."},
                        {"type": "tool_use", "id": "tu-1", "name": "Read", "input": {"file": "auth.py"}},
                    ],
                },
            },
            {
                "type": "user",
                "uuid": "u2",
                "sessionId": "ses-abc",
                "timestamp": "2025-06-01T09:00:06Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tu-1",
                            "content": "# auth.py\ndef login(): pass",
                        },
                    ],
                },
            },
            {
                "type": "progress",
                "sessionId": "ses-abc",
                "timestamp": "2025-06-01T09:00:07Z",
            },
            {
                "type": "assistant",
                "uuid": "a2",
                "sessionId": "ses-abc",
                "timestamp": "2025-06-01T09:00:10Z",
                "message": {
                    "model": "claude-opus-4-6",
                    "content": [
                        {"type": "text", "text": "I've implemented JWT auth."},
                    ],
                },
            },
            {
                "type": "result",
                "sessionId": "ses-abc",
                "timestamp": "2025-06-01T09:00:15Z",
            },
        ])

        meta, msgs = read_session_messages(path)

        # Metadata
        assert meta.session_id == "ses-abc"
        assert meta.slug == "implement-auth"
        assert meta.model == "claude-opus-4-6"
        assert meta.claude_code_version == "1.5.0"
        assert meta.started_at == "2025-06-01T09:00:00Z"
        assert meta.ended_at == "2025-06-01T09:00:15Z"

        # Messages (progress + result skipped = 5 messages from 6 entries)
        assert len(msgs) == 5

        # u1: user text
        assert msgs[0].role == "user"
        assert msgs[0].content == "Add JWT authentication"

        # a1-0: assistant text
        assert msgs[1].role == "assistant"
        assert msgs[1].id == "a1-0"

        # a1-1: tool_use
        assert msgs[2].role == "tool_use"
        assert msgs[2].id == "a1-1"
        assert msgs[2].metadata["tool_name"] == "Read"

        # u2: tool_result
        assert msgs[3].role == "tool_result"
        assert "auth.py" in msgs[3].content

        # a2: final assistant text
        assert msgs[4].role == "assistant"
        assert msgs[4].content == "I've implemented JWT auth."
