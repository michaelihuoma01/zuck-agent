"""Agent Runtime - Claude SDK wrapper for session lifecycle management.

This module wraps the claude-agent-sdk to provide:
- Session creation with async message streaming
- Session resumption using stored session IDs
- Multi-turn conversation support via ClaudeSDKClient
- Unified message format for API consumers
- Tool approval workflow via PreToolUse hooks
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Awaitable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    SystemMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    ThinkingBlock,
    HookMatcher,
    PreToolUseHookInput,
    HookContext,
)
from claude_agent_sdk import (
    ClaudeSDKError,
    CLINotFoundError,
    CLIConnectionError,
    ProcessError,
)

from src.core.exceptions import (
    AgentRuntimeError,
    AgentSessionError,
    AgentConnectionError,
    AgentNotConnectedError,
)
from src.core.types import AgentMessage
from src.core.constants import (
    DEFAULT_MODEL,
    DEFAULT_PERMISSION_MODE,
    DEFAULT_ALLOWED_TOOLS,
)
from src.core.approval_handler import ApprovalHandler, APPROVAL_TIMEOUT_SECONDS

# Type for approval callback
ApprovalCallback = Callable[[str, str, dict[str, Any], str], Awaitable[None]]

if TYPE_CHECKING:
    from src.config import Settings
    from src.models import Project

logger = logging.getLogger(__name__)


class AgentRuntime:
    """Wraps claude-agent-sdk to manage Claude Code sessions.

    This class provides session lifecycle management with:
    - New session creation with async message streaming
    - Session resumption using Claude's session IDs
    - Multi-turn conversation support
    - Unified message format for consumers
    - Tool approval workflow via PreToolUse hooks

    The runtime uses ClaudeSDKClient internally for:
    - Persistent conversation context
    - Hook support for approval workflow
    - Interrupt capability

    Example:
        runtime = AgentRuntime(settings)
        async for msg in runtime.start_session(project, "Add auth"):
            print(msg)  # AgentMessage dict
    """

    def __init__(
        self,
        settings: Settings,
        approval_handler: ApprovalHandler | None = None,
    ) -> None:
        """Initialize the agent runtime.

        Args:
            settings: Application settings with API key
            approval_handler: Handler for tool approval workflow (optional)
        """
        self._settings = settings
        self._approval_handler = approval_handler
        # Track active clients by our session ID for send_prompt()
        self._active_clients: dict[str, ClaudeSDKClient] = {}
        # Map our session IDs to Claude's session IDs
        self._session_id_map: dict[str, str] = {}
        # Callbacks for approval events
        self._approval_callbacks: dict[str, ApprovalCallback] = {}

    def set_approval_handler(self, handler: ApprovalHandler) -> None:
        """Set or update the approval handler.

        Args:
            handler: The approval handler instance
        """
        self._approval_handler = handler

    def set_approval_callback(
        self,
        session_id: str,
        callback: ApprovalCallback,
    ) -> None:
        """Set an approval callback for a session.

        The callback is called when a tool requires approval.
        Signature: async def callback(session_id, tool_name, tool_input, tool_use_id)

        Args:
            session_id: Our session ID
            callback: Async callback function
        """
        self._approval_callbacks[session_id] = callback

    def remove_approval_callback(self, session_id: str) -> None:
        """Remove the approval callback for a session.

        Args:
            session_id: Our session ID
        """
        self._approval_callbacks.pop(session_id, None)

    async def start_session(
        self,
        project: Project,
        prompt: str,
        session_id: str,
        *,
        model: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: list[str] | None = None,
        enable_approval_hooks: bool = False,
    ) -> AsyncIterator[AgentMessage]:
        """Start a new Claude session for a project.

        Creates a new ClaudeSDKClient, connects it, and streams
        messages back to the caller. The Claude session ID is
        captured from the init message and yielded first.

        Args:
            project: The project to run the session in
            prompt: The initial prompt to send
            session_id: Our internal session ID (for tracking)
            model: Model to use (defaults to claude-sonnet-4-5)
            permission_mode: Permission mode (defaults to "default")
            allowed_tools: List of allowed tools (defaults to standard set)
            enable_approval_hooks: If True, enable tool approval workflow

        Yields:
            AgentMessage dicts with streaming content

        Raises:
            AgentConnectionError: If SDK connection fails
            AgentSessionError: If session creation fails
        """
        # Validate project path exists
        project_path = Path(project.path)
        if not project_path.exists():
            raise AgentSessionError(f"Project path does not exist: {project.path}")

        # Build options
        options = self._build_options(
            project=project,
            model=model,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            session_id=session_id if enable_approval_hooks else None,
        )

        # Create and connect client
        client = ClaudeSDKClient(options=options)

        try:
            await client.connect()
            logger.info(f"Connected to Claude SDK for session {session_id}")

            # Store client for potential follow-up prompts
            self._active_clients[session_id] = client

            # Send initial prompt and stream responses
            await client.query(prompt)

            async for message in self._stream_response(client, session_id):
                yield message

        except CLINotFoundError as e:
            logger.error(f"Claude CLI not found: {e}")
            raise AgentConnectionError(
                "Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
            ) from e

        except CLIConnectionError as e:
            logger.error(f"Failed to connect to Claude: {e}")
            raise AgentConnectionError(f"Failed to connect to Claude SDK: {e}") from e

        except ProcessError as e:
            logger.error(f"Claude process error: {e}")
            raise AgentSessionError(f"Claude process failed: {e}") from e

        except ClaudeSDKError as e:
            logger.error(f"Claude SDK error: {e}")
            raise AgentRuntimeError(f"SDK error: {e}") from e

    async def resume_session(
        self,
        project: Project,
        prompt: str,
        session_id: str,
        claude_session_id: str,
        *,
        model: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: list[str] | None = None,
        enable_approval_hooks: bool = False,
    ) -> AsyncIterator[AgentMessage]:
        """Resume an existing Claude session.

        Uses the SDK's `resume` option to continue a previous
        conversation with full context preserved.

        Args:
            project: The project the session belongs to
            prompt: The prompt to send
            session_id: Our internal session ID
            claude_session_id: Claude's session ID to resume
            model: Model to use (optional)
            permission_mode: Permission mode (optional)
            allowed_tools: List of allowed tools (optional)
            enable_approval_hooks: If True, enable tool approval workflow

        Yields:
            AgentMessage dicts with streaming content

        Raises:
            AgentConnectionError: If SDK connection fails
            AgentSessionError: If resume fails
        """
        # Validate project path exists
        project_path = Path(project.path)
        if not project_path.exists():
            raise AgentSessionError(f"Project path does not exist: {project.path}")

        # Build options with resume
        options = self._build_options(
            project=project,
            model=model,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            resume=claude_session_id,
            session_id=session_id if enable_approval_hooks else None,
        )

        # Create and connect client
        client = ClaudeSDKClient(options=options)

        try:
            await client.connect()
            logger.info(f"Resuming Claude session {claude_session_id}")

            # Store client for potential follow-up prompts
            self._active_clients[session_id] = client
            self._session_id_map[session_id] = claude_session_id

            # Send prompt and stream responses
            await client.query(prompt)

            async for message in self._stream_response(client, session_id):
                yield message

        except CLINotFoundError as e:
            raise AgentConnectionError(
                "Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
            ) from e

        except CLIConnectionError as e:
            raise AgentConnectionError(f"Failed to connect to Claude SDK: {e}") from e

        except ProcessError as e:
            raise AgentSessionError(f"Claude process failed: {e}") from e

        except ClaudeSDKError as e:
            raise AgentRuntimeError(f"SDK error: {e}") from e

    async def send_prompt(
        self,
        session_id: str,
        prompt: str,
    ) -> AsyncIterator[AgentMessage]:
        """Send a prompt to an active session.

        This is for follow-up prompts in an already-connected session.
        The session must have been started with start_session() or
        resume_session() and still be active.

        Args:
            session_id: Our internal session ID
            prompt: The prompt to send

        Yields:
            AgentMessage dicts with streaming content

        Raises:
            AgentNotConnectedError: If session isn't active
            AgentSessionError: If sending fails
        """
        client = self._active_clients.get(session_id)
        if not client:
            raise AgentNotConnectedError(
                f"Session {session_id} is not connected. "
                "Use start_session() or resume_session() first."
            )

        try:
            await client.query(prompt)

            async for message in self._stream_response(client, session_id):
                yield message

        except ClaudeSDKError as e:
            raise AgentSessionError(f"Failed to send prompt: {e}") from e

    async def disconnect_session(self, session_id: str) -> None:
        """Disconnect and cleanup a session.

        Args:
            session_id: Our internal session ID
        """
        client = self._active_clients.pop(session_id, None)
        if client:
            try:
                await client.disconnect()
                logger.info(f"Disconnected session {session_id}")
            except Exception as e:
                logger.warning(f"Error disconnecting session {session_id}: {e}")

        self._session_id_map.pop(session_id, None)
        self._approval_callbacks.pop(session_id, None)

        # Clear any pending approval
        if self._approval_handler:
            await self._approval_handler.clear_pending(session_id)

    async def interrupt_session(self, session_id: str) -> None:
        """Interrupt a running session.

        Args:
            session_id: Our internal session ID

        Raises:
            AgentNotConnectedError: If session isn't active
        """
        client = self._active_clients.get(session_id)
        if not client:
            raise AgentNotConnectedError(f"Session {session_id} is not connected")

        try:
            await client.interrupt()
            logger.info(f"Interrupted session {session_id}")
        except ClaudeSDKError as e:
            logger.warning(f"Error interrupting session {session_id}: {e}")

    def get_claude_session_id(self, session_id: str) -> str | None:
        """Get the Claude session ID for our session ID.

        Args:
            session_id: Our internal session ID

        Returns:
            Claude's session ID or None if not mapped
        """
        return self._session_id_map.get(session_id)

    def is_session_active(self, session_id: str) -> bool:
        """Check if a session is currently active (connected).

        Args:
            session_id: Our internal session ID

        Returns:
            True if session has an active client connection
        """
        return session_id in self._active_clients

    async def stream_active_session(
        self, session_id: str
    ) -> AsyncIterator[AgentMessage]:
        """Stream messages from an active session.

        Public accessor for SSE/streaming endpoints that need to
        tap into an ongoing session's message stream.

        Args:
            session_id: Our internal session ID

        Yields:
            AgentMessage dicts

        Raises:
            AgentNotConnectedError: If session isn't active
        """
        client = self._active_clients.get(session_id)
        if not client:
            raise AgentNotConnectedError(
                f"Session {session_id} is not connected"
            )
        async for message in self._stream_response(client, session_id):
            yield message

    def _build_options(
        self,
        project: Project,
        *,
        model: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: list[str] | None = None,
        resume: str | None = None,
        session_id: str | None = None,
    ) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions for a session.

        Args:
            project: The project configuration
            model: Model override
            permission_mode: Permission mode override
            allowed_tools: Allowed tools override
            resume: Session ID to resume (optional)
            session_id: If provided, enables approval hooks for this session

        Returns:
            Configured ClaudeAgentOptions
        """
        # Use project defaults, then parameter overrides, then global defaults
        effective_tools = allowed_tools
        if effective_tools is None:
            project_tools = project.default_allowed_tools
            effective_tools = project_tools if project_tools else list(DEFAULT_ALLOWED_TOOLS)

        effective_mode = permission_mode
        if effective_mode is None:
            effective_mode = project.permission_mode or DEFAULT_PERMISSION_MODE

        effective_model = model or DEFAULT_MODEL

        options = ClaudeAgentOptions(
            cwd=project.path,
            model=effective_model,
            permission_mode=effective_mode,
            allowed_tools=effective_tools,
        )

        # Add resume if provided
        if resume:
            options.resume = resume

        # Add approval hooks if session_id provided and handler exists
        if session_id and self._approval_handler:
            options.hooks = {
                "PreToolUse": [
                    HookMatcher(
                        matcher="*",
                        hooks=[self._make_approval_hook(session_id)],
                    )
                ]
            }

        return options

    def _make_approval_hook(self, session_id: str):
        """Create a PreToolUse hook function for a specific session.

        The hook checks with the approval handler whether the tool
        requires approval. If so, it queues an approval request,
        notifies via callback, and waits for the user's decision.

        The SDK hook signature is:
            async def hook(input, tool_name, context) -> SyncHookJSONOutput

        Args:
            session_id: Our internal session ID

        Returns:
            Async hook function compatible with the SDK's HookCallback
        """
        handler = self._approval_handler

        async def approval_hook(
            hook_input: PreToolUseHookInput,
            tool_name_match: str | None,
            context: HookContext,
        ) -> dict[str, Any]:
            """PreToolUse hook that intercepts for approval.

            Args:
                hook_input: SDK hook input with tool_name, tool_input, tool_use_id
                tool_name_match: The matched tool name (from matcher pattern)
                context: Hook context

            Returns:
                SyncHookJSONOutput dict with permissionDecision
            """
            # SDK may pass hook_input as a dict or an object — handle both
            if isinstance(hook_input, dict):
                tool_name = hook_input.get("tool_name", "")
                tool_input = hook_input.get("tool_input", {})
                tool_use_id = hook_input.get("tool_use_id", "")
            else:
                tool_name = hook_input.tool_name
                tool_input = hook_input.tool_input
                tool_use_id = hook_input.tool_use_id

            if not handler.requires_approval(tool_name, tool_input):
                # Auto-approved - let tool proceed
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                    }
                }

            logger.info(
                f"Tool {tool_name} requires approval for session {session_id}"
            )

            # Queue the approval request
            request = await handler.queue_approval(
                session_id=session_id,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_use_id=tool_use_id,
            )

            # Notify via callback if registered
            callback = self._approval_callbacks.get(session_id)
            if callback:
                try:
                    await callback(session_id, tool_name, tool_input, tool_use_id)
                except Exception as e:
                    logger.warning(f"Approval callback error: {e}")

            # Wait for user decision (with timeout to prevent indefinite hangs)
            try:
                if APPROVAL_TIMEOUT_SECONDS > 0:
                    await asyncio.wait_for(
                        request.event.wait(),
                        timeout=APPROVAL_TIMEOUT_SECONDS,
                    )
                else:
                    await request.event.wait()
            except asyncio.TimeoutError:
                logger.warning(
                    f"Approval timed out for {tool_name} in session {session_id} "
                    f"after {APPROVAL_TIMEOUT_SECONDS}s"
                )
                # Clean up the pending request
                await handler.clear_pending(session_id)
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            f"Approval timed out after {APPROVAL_TIMEOUT_SECONDS} seconds"
                        ),
                    }
                }

            if request.approved:
                logger.info(f"Tool {tool_name} approved for session {session_id}")
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                    }
                }
            else:
                # Denied - provide feedback as the denial reason
                reason = request.feedback or f"User denied {tool_name} execution"
                logger.info(
                    f"Tool {tool_name} denied for session {session_id}: {reason}"
                )
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }

        return approval_hook

    async def _stream_response(
        self,
        client: ClaudeSDKClient,
        session_id: str,
    ) -> AsyncIterator[AgentMessage]:
        """Stream and process messages from the SDK client.

        Args:
            client: The connected ClaudeSDKClient
            session_id: Our internal session ID

        Yields:
            AgentMessage dicts
        """
        async for message in client.receive_response():
            for processed in self._process_message(message, session_id):
                # Capture Claude session ID from init message
                if processed.get("type") == "init" and processed.get("session_id"):
                    self._session_id_map[session_id] = processed["session_id"]

                yield processed

    def _process_message(
        self,
        message: Any,
        session_id: str,
    ) -> list[AgentMessage]:
        """Process an SDK message into our unified format.

        Args:
            message: Raw SDK message
            session_id: Our internal session ID

        Returns:
            List of AgentMessage dicts (may be empty)
        """
        # Handle SystemMessage (includes init with session ID)
        if isinstance(message, SystemMessage):
            result = self._process_system_message(message)
            return [result] if result else []

        # Handle AssistantMessage (text and tool use — may produce multiple messages)
        if isinstance(message, AssistantMessage):
            return self._process_assistant_message(message)

        # Handle ResultMessage (completion)
        if isinstance(message, ResultMessage):
            return [self._process_result_message(message, session_id)]

        # Log unknown message types for debugging
        logger.debug(f"Unhandled message type: {type(message).__name__}")
        return []

    def _process_system_message(self, message: SystemMessage) -> AgentMessage | None:
        """Process a SystemMessage from the SDK.

        Args:
            message: SystemMessage from SDK

        Returns:
            AgentMessage or None
        """
        if message.subtype == "init":
            # Extract session ID from init message
            claude_session_id = message.data.get("session_id")
            return AgentMessage(
                type="init",
                session_id=claude_session_id,
                raw_type="SystemMessage.init",
            )

        # Log other system message subtypes
        logger.debug(f"System message subtype: {message.subtype}")
        return None

    def _process_assistant_message(self, message: AssistantMessage) -> list[AgentMessage]:
        """Process an AssistantMessage from the SDK.

        AssistantMessage contains content blocks which can be:
        - TextBlock: Claude's text response
        - ToolUseBlock: Claude wants to use a tool
        - ThinkingBlock: Claude's thinking (for models with thinking)
        - ToolResultBlock: Result from tool execution

        A single AssistantMessage may contain multiple blocks (e.g.,
        text + tool_use). All blocks are returned as separate messages.

        Args:
            message: AssistantMessage from SDK

        Returns:
            List of AgentMessage dicts (one per content block)
        """
        results: list[AgentMessage] = []

        for block in message.content:
            if isinstance(block, TextBlock):
                results.append(AgentMessage(
                    type="text",
                    content=block.text,
                    model=message.model,
                    raw_type="AssistantMessage.TextBlock",
                ))

            elif isinstance(block, ToolUseBlock):
                results.append(AgentMessage(
                    type="tool_use",
                    tool_name=block.name,
                    tool_input=block.input,
                    tool_use_id=block.id,
                    model=message.model,
                    raw_type="AssistantMessage.ToolUseBlock",
                ))

            elif isinstance(block, ToolResultBlock):
                content = block.content
                # Content can be string or list of dicts
                if isinstance(content, list):
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                    content = "\n".join(text_parts)

                results.append(AgentMessage(
                    type="tool_result",
                    tool_use_id=block.tool_use_id,
                    tool_result=content or "",
                    is_error=block.is_error or False,
                    raw_type="AssistantMessage.ToolResultBlock",
                ))

            elif isinstance(block, ThinkingBlock):
                logger.debug(f"Thinking: {block.thinking[:100]}...")

        return results

    def _process_result_message(
        self,
        message: ResultMessage,
        session_id: str,
    ) -> AgentMessage:
        """Process a ResultMessage from the SDK.

        This indicates the session has completed (or errored).

        Args:
            message: ResultMessage from SDK
            session_id: Our internal session ID

        Returns:
            AgentMessage with completion data
        """
        is_complete = not message.is_error

        result = AgentMessage(
            type="result",
            session_id=message.session_id,
            is_complete=is_complete,
            total_cost_usd=message.total_cost_usd,
            duration_ms=message.duration_ms,
            num_turns=message.num_turns,
            raw_type="ResultMessage",
        )

        if message.is_error and message.result:
            result["content"] = message.result
            result["is_error"] = True

        return result

    async def cleanup(self) -> None:
        """Cleanup all active sessions.

        Call this during application shutdown.
        """
        session_ids = list(self._active_clients.keys())
        for session_id in session_ids:
            await self.disconnect_session(session_id)

        logger.info(f"Cleaned up {len(session_ids)} active sessions")
