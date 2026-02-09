"""Tests for AgentRuntime - Claude SDK wrapper.

This module contains both:
- Unit tests with mocked SDK (run without API key)
- Integration tests that call the real SDK (require ANTHROPIC_API_KEY)

Integration tests are marked with @pytest.mark.integration and skipped
if the API key is not available.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings
from src.core.agent_runtime import AgentRuntime
from src.core.exceptions import (
    AgentConnectionError,
    AgentNotConnectedError,
    AgentSessionError,
)
from src.models import Project


# Skip integration tests if no API key
HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
skip_without_api_key = pytest.mark.skipif(
    not HAS_API_KEY,
    reason="ANTHROPIC_API_KEY not set - skipping integration test",
)


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.anthropic_api_key = "test-api-key"
    return settings


@pytest.fixture
def real_settings() -> Settings:
    """Create real settings from environment for integration tests."""
    return Settings()


@pytest.fixture
def temp_project_path():
    """Create a temporary directory for test projects."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_project(temp_project_path: Path) -> Project:
    """Create a mock Project for testing."""
    project = MagicMock(spec=Project)
    project.id = "test-project-id"
    project.path = str(temp_project_path)
    project.name = "Test Project"
    project.default_allowed_tools = ["Read", "Write", "Bash"]
    project.permission_mode = "default"
    return project


@pytest.fixture
def runtime(mock_settings: Settings) -> AgentRuntime:
    """Create an AgentRuntime instance for testing."""
    return AgentRuntime(mock_settings)


# ============================================================================
# Unit Tests (mocked SDK)
# ============================================================================


class TestAgentRuntimeInit:
    """Tests for AgentRuntime initialization."""

    def test_init_creates_empty_client_tracking(self, runtime: AgentRuntime):
        """Runtime should initialize with empty client tracking."""
        assert runtime._active_clients == {}
        assert runtime._session_id_map == {}

    def test_init_stores_settings(self, mock_settings: Settings):
        """Runtime should store settings reference."""
        runtime = AgentRuntime(mock_settings)
        assert runtime._settings is mock_settings


class TestBuildOptions:
    """Tests for _build_options method."""

    def test_build_options_uses_project_defaults(
        self, runtime: AgentRuntime, mock_project: Project
    ):
        """Should use project's default tools and permission mode."""
        options = runtime._build_options(mock_project)

        assert options.cwd == mock_project.path
        assert options.allowed_tools == mock_project.default_allowed_tools
        assert options.permission_mode == mock_project.permission_mode

    def test_build_options_with_overrides(
        self, runtime: AgentRuntime, mock_project: Project
    ):
        """Should allow overriding project defaults."""
        custom_tools = ["Read", "Glob"]
        options = runtime._build_options(
            mock_project,
            model="claude-opus-4",
            permission_mode="acceptEdits",
            allowed_tools=custom_tools,
        )

        assert options.model == "claude-opus-4"
        assert options.permission_mode == "acceptEdits"
        assert options.allowed_tools == custom_tools

    def test_build_options_with_resume(
        self, runtime: AgentRuntime, mock_project: Project
    ):
        """Should set resume option when provided."""
        options = runtime._build_options(
            mock_project,
            resume="claude-session-123",
        )

        assert options.resume == "claude-session-123"

    def test_build_options_uses_global_defaults_when_project_has_none(
        self, runtime: AgentRuntime, mock_project: Project
    ):
        """Should fall back to global defaults when project has no config."""
        mock_project.default_allowed_tools = None
        mock_project.permission_mode = None

        options = runtime._build_options(mock_project)

        from src.core.constants import DEFAULT_ALLOWED_TOOLS, DEFAULT_PERMISSION_MODE

        assert options.allowed_tools == list(DEFAULT_ALLOWED_TOOLS)
        assert options.permission_mode == DEFAULT_PERMISSION_MODE


class TestSessionIdTracking:
    """Tests for session ID mapping."""

    def test_get_claude_session_id_returns_none_for_unknown(
        self, runtime: AgentRuntime
    ):
        """Should return None for unknown session."""
        assert runtime.get_claude_session_id("unknown-id") is None

    def test_get_claude_session_id_returns_mapped_id(self, runtime: AgentRuntime):
        """Should return Claude session ID when mapped."""
        runtime._session_id_map["our-id"] = "claude-id"
        assert runtime.get_claude_session_id("our-id") == "claude-id"

    def test_is_session_active_false_for_unknown(self, runtime: AgentRuntime):
        """Should return False for unknown session."""
        assert runtime.is_session_active("unknown-id") is False

    def test_is_session_active_true_for_active(self, runtime: AgentRuntime):
        """Should return True when client exists."""
        runtime._active_clients["active-id"] = MagicMock()
        assert runtime.is_session_active("active-id") is True


class TestProcessMessages:
    """Tests for message processing methods."""

    def test_process_system_init_message(self, runtime: AgentRuntime):
        """Should extract session ID from init message."""
        from claude_agent_sdk import SystemMessage

        mock_msg = MagicMock(spec=SystemMessage)
        mock_msg.subtype = "init"
        mock_msg.data = {"session_id": "claude-123"}

        result = runtime._process_system_message(mock_msg)

        assert result["type"] == "init"
        assert result["session_id"] == "claude-123"

    def test_process_system_non_init_message(self, runtime: AgentRuntime):
        """Should return None for non-init system messages."""
        from claude_agent_sdk import SystemMessage

        mock_msg = MagicMock(spec=SystemMessage)
        mock_msg.subtype = "other"

        result = runtime._process_system_message(mock_msg)
        assert result is None

    def test_process_text_block(self, runtime: AgentRuntime):
        """Should process TextBlock into text message."""
        from claude_agent_sdk import AssistantMessage, TextBlock

        text_block = MagicMock(spec=TextBlock)
        text_block.text = "Hello, I can help you."

        mock_msg = MagicMock(spec=AssistantMessage)
        mock_msg.content = [text_block]
        mock_msg.model = "claude-sonnet-4-5"

        results = runtime._process_assistant_message(mock_msg)

        assert len(results) == 1
        assert results[0]["type"] == "text"
        assert results[0]["content"] == "Hello, I can help you."
        assert results[0]["model"] == "claude-sonnet-4-5"

    def test_process_tool_use_block(self, runtime: AgentRuntime):
        """Should process ToolUseBlock into tool_use message."""
        from claude_agent_sdk import AssistantMessage, ToolUseBlock

        tool_block = MagicMock(spec=ToolUseBlock)
        tool_block.name = "Read"
        tool_block.input = {"file_path": "/test/file.py"}
        tool_block.id = "tool-123"

        mock_msg = MagicMock(spec=AssistantMessage)
        mock_msg.content = [tool_block]
        mock_msg.model = "claude-sonnet-4-5"

        results = runtime._process_assistant_message(mock_msg)

        assert len(results) == 1
        assert results[0]["type"] == "tool_use"
        assert results[0]["tool_name"] == "Read"
        assert results[0]["tool_input"] == {"file_path": "/test/file.py"}
        assert results[0]["tool_use_id"] == "tool-123"

    def test_process_tool_result_block(self, runtime: AgentRuntime):
        """Should process ToolResultBlock into tool_result message."""
        from claude_agent_sdk import AssistantMessage, ToolResultBlock

        result_block = MagicMock(spec=ToolResultBlock)
        result_block.tool_use_id = "tool-123"
        result_block.content = "File contents here"
        result_block.is_error = False

        mock_msg = MagicMock(spec=AssistantMessage)
        mock_msg.content = [result_block]
        mock_msg.model = "claude-sonnet-4-5"

        results = runtime._process_assistant_message(mock_msg)

        assert len(results) == 1
        assert results[0]["type"] == "tool_result"
        assert results[0]["tool_use_id"] == "tool-123"
        assert results[0]["tool_result"] == "File contents here"
        assert results[0]["is_error"] is False

    def test_process_multi_block_message(self, runtime: AgentRuntime):
        """Should process all blocks in a multi-block AssistantMessage."""
        from claude_agent_sdk import AssistantMessage, TextBlock, ToolUseBlock

        text_block = MagicMock(spec=TextBlock)
        text_block.text = "I'll read the file."

        tool_block = MagicMock(spec=ToolUseBlock)
        tool_block.name = "Read"
        tool_block.input = {"file_path": "/test.py"}
        tool_block.id = "tool-456"

        mock_msg = MagicMock(spec=AssistantMessage)
        mock_msg.content = [text_block, tool_block]
        mock_msg.model = "claude-sonnet-4-5"

        results = runtime._process_assistant_message(mock_msg)

        assert len(results) == 2
        assert results[0]["type"] == "text"
        assert results[1]["type"] == "tool_use"
        assert results[1]["tool_name"] == "Read"

    def test_process_result_message(self, runtime: AgentRuntime):
        """Should process ResultMessage into result message."""
        from claude_agent_sdk import ResultMessage

        mock_msg = MagicMock(spec=ResultMessage)
        mock_msg.session_id = "claude-123"
        mock_msg.is_error = False
        mock_msg.total_cost_usd = 0.025
        mock_msg.duration_ms = 5000
        mock_msg.num_turns = 3
        mock_msg.result = None

        result = runtime._process_result_message(mock_msg, "our-session-id")

        assert result["type"] == "result"
        assert result["session_id"] == "claude-123"
        assert result["is_complete"] is True
        assert result["total_cost_usd"] == 0.025
        assert result["duration_ms"] == 5000

    def test_process_result_message_with_error(self, runtime: AgentRuntime):
        """Should include error content when session failed."""
        from claude_agent_sdk import ResultMessage

        mock_msg = MagicMock(spec=ResultMessage)
        mock_msg.session_id = "claude-123"
        mock_msg.is_error = True
        mock_msg.result = "Something went wrong"
        mock_msg.total_cost_usd = 0.01
        mock_msg.duration_ms = 1000
        mock_msg.num_turns = 1

        result = runtime._process_result_message(mock_msg, "our-session-id")

        assert result["type"] == "result"
        assert result["is_complete"] is False
        assert result["is_error"] is True
        assert result["content"] == "Something went wrong"


class TestStartSessionErrors:
    """Tests for start_session error handling."""

    @pytest.mark.asyncio
    async def test_start_session_invalid_path(
        self, runtime: AgentRuntime, mock_project: Project
    ):
        """Should raise AgentSessionError for non-existent path."""
        mock_project.path = "/nonexistent/path"

        with pytest.raises(AgentSessionError, match="does not exist"):
            async for _ in runtime.start_session(
                mock_project, "test prompt", "session-id"
            ):
                pass

    @pytest.mark.asyncio
    async def test_start_session_cli_not_found(
        self, runtime: AgentRuntime, mock_project: Project
    ):
        """Should raise AgentConnectionError when CLI not found."""
        from claude_agent_sdk import CLINotFoundError

        with patch(
            "src.core.agent_runtime.ClaudeSDKClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect.side_effect = CLINotFoundError()
            mock_client_class.return_value = mock_client

            with pytest.raises(AgentConnectionError, match="CLI not found"):
                async for _ in runtime.start_session(
                    mock_project, "test prompt", "session-id"
                ):
                    pass


class TestSendPromptErrors:
    """Tests for send_prompt error handling."""

    @pytest.mark.asyncio
    async def test_send_prompt_not_connected(self, runtime: AgentRuntime):
        """Should raise AgentNotConnectedError when session not active."""
        with pytest.raises(AgentNotConnectedError, match="not connected"):
            async for _ in runtime.send_prompt("unknown-session", "test"):
                pass


class TestDisconnectSession:
    """Tests for disconnect_session."""

    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self, runtime: AgentRuntime):
        """Should remove client and session mapping."""
        mock_client = AsyncMock()
        runtime._active_clients["test-session"] = mock_client
        runtime._session_id_map["test-session"] = "claude-id"

        await runtime.disconnect_session("test-session")

        assert "test-session" not in runtime._active_clients
        assert "test-session" not in runtime._session_id_map
        mock_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_handles_missing_session(self, runtime: AgentRuntime):
        """Should handle disconnect for non-existent session gracefully."""
        # Should not raise
        await runtime.disconnect_session("nonexistent")


class TestCleanup:
    """Tests for cleanup method."""

    @pytest.mark.asyncio
    async def test_cleanup_disconnects_all_sessions(self, runtime: AgentRuntime):
        """Should disconnect all active sessions."""
        client1 = AsyncMock()
        client2 = AsyncMock()
        runtime._active_clients = {
            "session-1": client1,
            "session-2": client2,
        }

        await runtime.cleanup()

        assert runtime._active_clients == {}
        client1.disconnect.assert_called_once()
        client2.disconnect.assert_called_once()


# ============================================================================
# Integration Tests (require API key)
# ============================================================================


@pytest.mark.integration
class TestAgentRuntimeIntegration:
    """Integration tests that call the real Claude SDK.

    These tests require ANTHROPIC_API_KEY to be set and will actually
    make API calls. They test the full flow of session management.
    """

    @skip_without_api_key
    @pytest.mark.asyncio
    async def test_start_session_captures_session_id(
        self, real_settings: Settings, temp_project_path: Path
    ):
        """Starting a session should capture Claude's session ID."""
        # Create a real project pointing to temp directory
        project = MagicMock(spec=Project)
        project.id = "integration-test-project"
        project.path = str(temp_project_path)
        project.default_allowed_tools = ["Read"]
        project.permission_mode = "acceptEdits"

        runtime = AgentRuntime(real_settings)
        session_id = "test-session-123"

        try:
            messages = []
            async for msg in runtime.start_session(
                project,
                "Say 'hello' and nothing else",
                session_id,
                model="claude-sonnet-4-5",
            ):
                messages.append(msg)

                # Stop after getting init message to minimize API usage
                if msg.get("type") == "init":
                    break

            # Should have captured Claude's session ID
            assert runtime.get_claude_session_id(session_id) is not None
            assert any(m.get("type") == "init" for m in messages)

        finally:
            await runtime.cleanup()

    @skip_without_api_key
    @pytest.mark.asyncio
    async def test_start_session_streams_text_response(
        self, real_settings: Settings, temp_project_path: Path
    ):
        """Starting a session should stream text responses."""
        project = MagicMock(spec=Project)
        project.id = "integration-test-project"
        project.path = str(temp_project_path)
        project.default_allowed_tools = []  # No tools to keep response simple
        project.permission_mode = "acceptEdits"

        runtime = AgentRuntime(real_settings)

        try:
            messages = []
            async for msg in runtime.start_session(
                project,
                "Reply with exactly: TEST_SUCCESS",
                "test-session",
                model="claude-sonnet-4-5",
            ):
                messages.append(msg)

            # Should have text response
            text_messages = [m for m in messages if m.get("type") == "text"]
            assert len(text_messages) > 0

            # Should have result message
            result_messages = [m for m in messages if m.get("type") == "result"]
            assert len(result_messages) == 1
            assert result_messages[0].get("is_complete") is True

        finally:
            await runtime.cleanup()

    @skip_without_api_key
    @pytest.mark.asyncio
    async def test_full_session_lifecycle(
        self, real_settings: Settings, temp_project_path: Path
    ):
        """Test start, send_prompt, and disconnect cycle."""
        project = MagicMock(spec=Project)
        project.id = "lifecycle-test-project"
        project.path = str(temp_project_path)
        project.default_allowed_tools = []
        project.permission_mode = "acceptEdits"

        runtime = AgentRuntime(real_settings)
        session_id = "lifecycle-session"

        try:
            # Start session
            first_messages = []
            async for msg in runtime.start_session(
                project,
                "Remember this number: 42. Reply with OK.",
                session_id,
                model="claude-sonnet-4-5",
            ):
                first_messages.append(msg)

            assert runtime.is_session_active(session_id)
            claude_id = runtime.get_claude_session_id(session_id)
            assert claude_id is not None

            # Send follow-up prompt
            follow_up_messages = []
            async for msg in runtime.send_prompt(
                session_id,
                "What number did I ask you to remember?",
            ):
                follow_up_messages.append(msg)

            # Should get a response mentioning 42
            text_content = " ".join(
                m.get("content", "") for m in follow_up_messages if m.get("type") == "text"
            )
            assert "42" in text_content

        finally:
            await runtime.disconnect_session(session_id)
            assert not runtime.is_session_active(session_id)

    @skip_without_api_key
    @pytest.mark.asyncio
    async def test_resume_session(
        self, real_settings: Settings, temp_project_path: Path
    ):
        """Test resuming a session with stored Claude session ID."""
        project = MagicMock(spec=Project)
        project.id = "resume-test-project"
        project.path = str(temp_project_path)
        project.default_allowed_tools = []
        project.permission_mode = "acceptEdits"

        runtime = AgentRuntime(real_settings)

        try:
            # Start initial session
            session_id_1 = "original-session"
            async for msg in runtime.start_session(
                project,
                "Remember the word: PINEAPPLE. Reply with OK.",
                session_id_1,
                model="claude-sonnet-4-5",
            ):
                pass

            # Get Claude's session ID
            claude_session_id = runtime.get_claude_session_id(session_id_1)
            assert claude_session_id is not None

            # Disconnect original session
            await runtime.disconnect_session(session_id_1)

            # Resume with new internal session ID
            session_id_2 = "resumed-session"
            resume_messages = []
            async for msg in runtime.resume_session(
                project,
                "What word did I ask you to remember?",
                session_id_2,
                claude_session_id,
                model="claude-sonnet-4-5",
            ):
                resume_messages.append(msg)

            # Should remember the word
            text_content = " ".join(
                m.get("content", "").upper()
                for m in resume_messages
                if m.get("type") == "text"
            )
            assert "PINEAPPLE" in text_content

        finally:
            await runtime.cleanup()
