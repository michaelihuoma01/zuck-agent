"""Tests for Claude Code session discovery utility."""

import json
import os
from pathlib import Path

import pytest

from src.utils.session_discovery import (
    ExternalSession,
    encode_project_path,
    discover_session,
    discover_sessions,
    _parse_metadata_fields,
    _extract_first_user_message,
    CLAUDE_PROJECTS_DIR,
)


# =============================================================================
# encode_project_path
# =============================================================================


class TestEncodeProjectPath:
    def test_basic_path(self):
        assert encode_project_path("/Users/mike/Documents/zuck") == "-Users-mike-Documents-zuck"

    def test_root_path(self):
        assert encode_project_path("/") == "-"

    def test_trailing_slash(self):
        assert encode_project_path("/Users/mike/project/") == "-Users-mike-project"

    def test_double_slash(self):
        """os.path.normpath collapses double slashes."""
        assert encode_project_path("/Users//mike/project") == "-Users-mike-project"

    def test_relative_dot(self):
        """os.path.normpath resolves dots."""
        assert encode_project_path("/Users/mike/./project") == "-Users-mike-project"

    def test_deeply_nested(self):
        assert encode_project_path("/a/b/c/d/e/f") == "-a-b-c-d-e-f"


# =============================================================================
# Helpers
# =============================================================================


def _make_jsonl_entry(
    entry_type: str = "user",
    session_id: str = "test-session-1",
    timestamp: str = "2026-01-15T10:00:00.000Z",
    **extra,
) -> str:
    """Create a single JSONL entry."""
    entry = {
        "type": entry_type,
        "sessionId": session_id,
        "timestamp": timestamp,
        "uuid": "uuid-1",
        "parentUuid": None,
        **extra,
    }
    return json.dumps(entry)


def _make_assistant_entry(
    session_id: str = "test-session-1",
    timestamp: str = "2026-01-15T10:05:00.000Z",
    model: str = "claude-opus-4-6",
) -> str:
    return json.dumps({
        "type": "assistant",
        "sessionId": session_id,
        "timestamp": timestamp,
        "uuid": "uuid-2",
        "parentUuid": "uuid-1",
        "message": {
            "model": model,
            "id": "msg_123",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello!"}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
    })


def _create_session_file(
    directory: Path,
    session_id: str = "abc12345-1234-5678-abcd-123456789abc",
    num_user: int = 3,
    num_assistant: int = 5,
    slug: str | None = "spicy-zooming-quail",
    version: str = "2.1.33",
    model: str = "claude-opus-4-6",
    create_subagents: bool = False,
) -> Path:
    """Create a realistic JSONL session file."""
    lines = []

    # First entry (user)
    extra = {}
    if slug:
        extra["slug"] = slug
    if version:
        extra["version"] = version
    lines.append(_make_jsonl_entry(
        entry_type="user",
        session_id=session_id,
        timestamp="2026-01-15T10:00:00.000Z",
        **extra,
    ))

    # Mix of user and assistant entries
    for i in range(num_assistant):
        lines.append(_make_assistant_entry(
            session_id=session_id,
            timestamp=f"2026-01-15T10:{10 + i:02d}:00.000Z",
            model=model,
        ))

    for i in range(num_user - 1):  # -1 because first entry is user
        lines.append(_make_jsonl_entry(
            entry_type="user",
            session_id=session_id,
            timestamp=f"2026-01-15T10:{20 + i:02d}:00.000Z",
        ))

    # Last entry
    lines.append(_make_jsonl_entry(
        entry_type="user",
        session_id=session_id,
        timestamp="2026-01-15T11:30:00.000Z",
    ))

    file_path = directory / f"{session_id}.jsonl"
    file_path.write_text("\n".join(lines) + "\n")

    if create_subagents:
        subagent_dir = directory / session_id / "subagents"
        subagent_dir.mkdir(parents=True)
        (subagent_dir / "agent-1.jsonl").write_text(
            _make_jsonl_entry(entry_type="user", session_id="sub-1") + "\n"
        )

    return file_path


# =============================================================================
# discover_session (single file)
# =============================================================================


class TestDiscoverSession:
    def test_basic_session(self, tmp_path: Path):
        file_path = _create_session_file(tmp_path)
        session = discover_session(file_path)

        assert session is not None
        assert session.session_id == "abc12345-1234-5678-abcd-123456789abc"
        assert session.slug == "spicy-zooming-quail"
        assert session.started_at == "2026-01-15T10:00:00.000Z"
        assert session.ended_at == "2026-01-15T11:30:00.000Z"
        assert session.model == "claude-opus-4-6"
        assert session.claude_code_version == "2.1.33"
        assert session.file_size_bytes > 0
        assert session.user_messages >= 3
        assert session.assistant_messages >= 5

    def test_no_slug(self, tmp_path: Path):
        file_path = _create_session_file(tmp_path, slug=None)
        session = discover_session(file_path)
        assert session is not None
        assert session.slug is None

    def test_with_subagents(self, tmp_path: Path):
        file_path = _create_session_file(tmp_path, create_subagents=True)
        session = discover_session(file_path)
        assert session is not None
        assert session.has_subagents is True

    def test_without_subagents(self, tmp_path: Path):
        file_path = _create_session_file(tmp_path)
        session = discover_session(file_path)
        assert session is not None
        assert session.has_subagents is False

    def test_empty_file(self, tmp_path: Path):
        file_path = tmp_path / "empty.jsonl"
        file_path.write_text("")
        session = discover_session(file_path)
        assert session is None

    def test_invalid_json(self, tmp_path: Path):
        file_path = tmp_path / "bad.jsonl"
        file_path.write_text("not json\n")
        session = discover_session(file_path)
        assert session is None

    def test_model_detection(self, tmp_path: Path):
        file_path = _create_session_file(
            tmp_path,
            session_id="model-test-1234-5678-abcd-123456789abc",
            model="claude-sonnet-4-5-20250929",
        )
        session = discover_session(file_path)
        assert session is not None
        assert session.model == "claude-sonnet-4-5-20250929"

    def test_total_entries(self, tmp_path: Path):
        file_path = _create_session_file(
            tmp_path,
            session_id="count-test-1234-5678-abcd-123456789abc",
            num_user=10,
            num_assistant=20,
        )
        session = discover_session(file_path)
        assert session is not None
        # 10 user + 20 assistant + 1 trailing user = 31
        assert session.total_entries >= 30

    def test_nonexistent_file(self, tmp_path: Path):
        file_path = tmp_path / "nonexistent.jsonl"
        session = discover_session(file_path)
        assert session is None


# =============================================================================
# discover_sessions (project-level scan)
# =============================================================================


class TestDiscoverSessions:
    def test_no_claude_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Returns empty list when .claude/projects dir doesn't exist."""
        monkeypatch.setattr(
            "src.utils.session_discovery.CLAUDE_PROJECTS_DIR",
            tmp_path / ".claude" / "projects",
        )
        result = discover_sessions("/nonexistent/project")
        assert result == []

    def test_no_matching_project(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Returns empty list when the encoded project dir doesn't exist."""
        claude_dir = tmp_path / ".claude" / "projects"
        claude_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "src.utils.session_discovery.CLAUDE_PROJECTS_DIR",
            claude_dir,
        )
        result = discover_sessions("/Users/mike/nonexistent-project")
        assert result == []

    def test_discovers_multiple_sessions(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Finds all JSONL files in the project directory."""
        claude_dir = tmp_path / ".claude" / "projects"
        project_dir = claude_dir / "-test-project"
        project_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "src.utils.session_discovery.CLAUDE_PROJECTS_DIR",
            claude_dir,
        )

        _create_session_file(
            project_dir,
            session_id="session-a-1234-5678-abcd-123456789abc",
            slug="alpha-session",
        )
        _create_session_file(
            project_dir,
            session_id="session-b-1234-5678-abcd-123456789abc",
            slug="beta-session",
        )
        _create_session_file(
            project_dir,
            session_id="session-c-1234-5678-abcd-123456789abc",
            slug="gamma-session",
        )

        result = discover_sessions("/test/project")
        assert len(result) == 3
        slugs = {s.slug for s in result}
        assert slugs == {"alpha-session", "beta-session", "gamma-session"}

    def test_sorted_newest_first(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Sessions are sorted by started_at descending."""
        claude_dir = tmp_path / ".claude" / "projects"
        project_dir = claude_dir / "-sort-test"
        project_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "src.utils.session_discovery.CLAUDE_PROJECTS_DIR",
            claude_dir,
        )

        # Create sessions — they'll all have the same started_at from _create_session_file
        # so we need to override timestamps manually
        for i, sid in enumerate(["old", "mid", "new"]):
            full_id = f"{sid}-session-1234-5678-abcd-123456789abc"
            entry = json.dumps({
                "type": "user",
                "sessionId": full_id,
                "timestamp": f"2026-0{i + 1}-01T10:00:00.000Z",
                "slug": f"{sid}-slug",
                "version": "2.1.33",
            })
            (project_dir / f"{full_id}.jsonl").write_text(entry + "\n")

        result = discover_sessions("/sort/test")
        assert len(result) == 3
        assert result[0].slug == "new-slug"
        assert result[1].slug == "mid-slug"
        assert result[2].slug == "old-slug"

    def test_skips_empty_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Empty JSONL files are skipped."""
        claude_dir = tmp_path / ".claude" / "projects"
        project_dir = claude_dir / "-skip-test"
        project_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "src.utils.session_discovery.CLAUDE_PROJECTS_DIR",
            claude_dir,
        )

        _create_session_file(
            project_dir,
            session_id="good-session-1234-5678-abcd-123456789abc",
        )
        (project_dir / "empty-session.jsonl").write_text("")

        result = discover_sessions("/skip/test")
        assert len(result) == 1
        assert result[0].session_id == "good-session-1234-5678-abcd-123456789abc"

    def test_ignores_non_jsonl_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Only .jsonl files are scanned."""
        claude_dir = tmp_path / ".claude" / "projects"
        project_dir = claude_dir / "-ignore-test"
        project_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "src.utils.session_discovery.CLAUDE_PROJECTS_DIR",
            claude_dir,
        )

        _create_session_file(
            project_dir,
            session_id="valid-sess-1234-5678-abcd-123456789abc",
        )
        # Create non-JSONL files that should be ignored
        (project_dir / "notes.txt").write_text("not a session")
        (project_dir / "memory").mkdir(exist_ok=True)
        (project_dir / "memory" / "MEMORY.md").write_text("# Memory")

        result = discover_sessions("/ignore/test")
        assert len(result) == 1


# =============================================================================
# discover_sessions with real Claude dir (live test, skipped in CI)
# =============================================================================


@pytest.mark.skipif(
    not CLAUDE_PROJECTS_DIR.is_dir(),
    reason="No ~/.claude/projects directory found",
)
class TestLiveDiscovery:
    """Integration tests that run against real Claude Code session data."""

    def test_discover_real_sessions(self):
        """Find sessions for the ZURK project itself (if they exist)."""
        result = discover_sessions("/Users/magikmike/Documents/zuck")
        # We know there are sessions from the earlier exploration
        assert len(result) > 0
        for session in result:
            assert session.session_id
            assert session.file_size_bytes > 0
            assert session.total_entries > 0

    def test_session_has_expected_fields(self):
        """Verify a discovered session has reasonable metadata."""
        result = discover_sessions("/Users/magikmike/Documents/zuck")
        if not result:
            pytest.skip("No sessions found")

        session = result[0]
        assert session.started_at is not None
        assert session.ended_at is not None
        assert session.model is not None
        assert "claude" in session.model


# =============================================================================
# _parse_metadata_fields
# =============================================================================


class TestParseMetadataFields:
    """Tests for the _parse_metadata_fields helper."""

    def test_metadata_on_first_line(self, tmp_path: Path):
        """Fields found on line 1 are returned."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text(json.dumps({
            "type": "user",
            "slug": "first-slug",
            "cwd": "/home/user/project",
            "gitBranch": "main",
        }) + "\n")

        result = _parse_metadata_fields(file_path)
        assert result["slug"] == "first-slug"
        assert result["cwd"] == "/home/user/project"
        assert result["gitBranch"] == "main"

    def test_metadata_on_later_lines(self, tmp_path: Path):
        """Fields on lines 2-3 are found when line 1 is file-history-snapshot."""
        lines = [
            json.dumps({"type": "file-history-snapshot", "sessionId": "s1"}),
            json.dumps({"type": "user", "slug": "later-slug", "cwd": "/opt/project"}),
            json.dumps({"type": "user", "gitBranch": "feature-x"}),
        ]
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("\n".join(lines) + "\n")

        result = _parse_metadata_fields(file_path)
        assert result["slug"] == "later-slug"
        assert result["cwd"] == "/opt/project"
        assert result["gitBranch"] == "feature-x"

    def test_missing_fields_returns_partial(self, tmp_path: Path):
        """Only found fields are present in the result dict."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text(json.dumps({
            "type": "user",
            "slug": "only-slug",
        }) + "\n")

        result = _parse_metadata_fields(file_path)
        assert result["slug"] == "only-slug"
        assert "cwd" not in result
        assert "gitBranch" not in result

    def test_empty_file(self, tmp_path: Path):
        """Empty file returns empty dict."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("")

        result = _parse_metadata_fields(file_path)
        assert result == {}

    def test_nonexistent_file(self, tmp_path: Path):
        """Nonexistent file returns empty dict (no exception)."""
        file_path = tmp_path / "nonexistent.jsonl"
        result = _parse_metadata_fields(file_path)
        assert result == {}

    def test_first_value_wins(self, tmp_path: Path):
        """If slug appears on multiple lines, the first occurrence wins."""
        lines = [
            json.dumps({"type": "user", "slug": "first"}),
            json.dumps({"type": "user", "slug": "second"}),
        ]
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("\n".join(lines) + "\n")

        result = _parse_metadata_fields(file_path)
        assert result["slug"] == "first"


# =============================================================================
# discover_session with new fields (cwd, git_branch)
# =============================================================================


class TestDiscoverSessionNewFields:
    """Tests that discover_session populates cwd and git_branch."""

    def test_cwd_and_git_branch_populated(self, tmp_path: Path):
        """discover_session extracts cwd and git_branch from metadata."""
        session_id = "meta-test-1234-5678-abcd-123456789abc"
        lines = [
            json.dumps({
                "type": "user",
                "sessionId": session_id,
                "timestamp": "2026-01-15T10:00:00.000Z",
                "slug": "test-slug",
                "version": "2.1.33",
                "cwd": "/home/user/myproject",
                "gitBranch": "develop",
            }),
            _make_assistant_entry(session_id=session_id),
        ]
        file_path = tmp_path / f"{session_id}.jsonl"
        file_path.write_text("\n".join(lines) + "\n")

        session = discover_session(file_path)
        assert session is not None
        assert session.cwd == "/home/user/myproject"
        assert session.git_branch == "develop"

    def test_missing_cwd_and_git_branch(self, tmp_path: Path):
        """When cwd/gitBranch are absent, fields are None."""
        file_path = _create_session_file(tmp_path)
        session = discover_session(file_path)
        assert session is not None
        assert session.cwd is None
        assert session.git_branch is None


# =============================================================================
# _extract_first_user_message
# =============================================================================


class TestExtractFirstUserMessage:
    """Tests for the _extract_first_user_message helper."""

    def test_string_content(self, tmp_path: Path):
        """Extracts plain string content from first user message."""
        lines = [
            json.dumps({"type": "file-history-snapshot", "sessionId": "s1"}),
            json.dumps({
                "type": "user",
                "sessionId": "s1",
                "message": {"role": "user", "content": "Build me a dashboard"},
            }),
        ]
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("\n".join(lines) + "\n")

        result = _extract_first_user_message(file_path)
        assert result == "Build me a dashboard"

    def test_list_content_blocks(self, tmp_path: Path):
        """Extracts text from content block array."""
        lines = [
            json.dumps({
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze the codebase"},
                    ],
                },
            }),
        ]
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("\n".join(lines) + "\n")

        result = _extract_first_user_message(file_path)
        assert result == "Analyze the codebase"

    def test_skips_non_user_entries(self, tmp_path: Path):
        """Non-user entries are skipped until first user entry found."""
        lines = [
            json.dumps({"type": "file-history-snapshot"}),
            json.dumps({"type": "progress"}),
            json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hi"}]}}),
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "Hello Claude"},
            }),
        ]
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("\n".join(lines) + "\n")

        result = _extract_first_user_message(file_path)
        assert result == "Hello Claude"

    def test_empty_file(self, tmp_path: Path):
        """Empty file returns None."""
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("")

        result = _extract_first_user_message(file_path)
        assert result is None

    def test_no_user_messages(self, tmp_path: Path):
        """File without user messages returns None."""
        lines = [
            json.dumps({"type": "file-history-snapshot"}),
            json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hi"}]}}),
        ]
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("\n".join(lines) + "\n")

        result = _extract_first_user_message(file_path)
        assert result is None

    def test_nonexistent_file(self, tmp_path: Path):
        """Nonexistent file returns None (no exception)."""
        result = _extract_first_user_message(tmp_path / "nope.jsonl")
        assert result is None

    def test_interrupted_message(self, tmp_path: Path):
        """Interrupted messages (with bracket syntax) are preserved."""
        lines = [
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "[Request interrupted by user for tool use]"},
            }),
        ]
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("\n".join(lines) + "\n")

        result = _extract_first_user_message(file_path)
        assert result == "[Request interrupted by user for tool use]"

    def test_whitespace_stripped(self, tmp_path: Path):
        """Leading/trailing whitespace is stripped."""
        lines = [
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "  Fix the bug  \n"},
            }),
        ]
        file_path = tmp_path / "test.jsonl"
        file_path.write_text("\n".join(lines) + "\n")

        result = _extract_first_user_message(file_path)
        assert result == "Fix the bug"


class TestDiscoverSessionTitle:
    """Tests that discover_session populates the title field."""

    def test_title_from_first_user_message(self, tmp_path: Path):
        """discover_session extracts the first user message as title."""
        session_id = "title-test-1234-5678-abcd-123456789abc"
        lines = [
            json.dumps({
                "type": "user",
                "sessionId": session_id,
                "timestamp": "2026-01-15T10:00:00.000Z",
                "slug": "test-slug",
                "version": "2.1.33",
                "message": {"role": "user", "content": "Build a REST API"},
            }),
            _make_assistant_entry(session_id=session_id),
        ]
        file_path = tmp_path / f"{session_id}.jsonl"
        file_path.write_text("\n".join(lines) + "\n")

        session = discover_session(file_path)
        assert session is not None
        assert session.title == "Build a REST API"

    def test_title_none_when_no_user_content(self, tmp_path: Path):
        """title is None when user entries lack message content."""
        file_path = _create_session_file(tmp_path)
        session = discover_session(file_path)
        assert session is not None
        # _create_session_file uses _make_jsonl_entry which doesn't set message.content
        assert session.title is None
