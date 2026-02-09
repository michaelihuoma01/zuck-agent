"""Approval Handler - Tool approval logic and workflow management.

This module determines which tool uses require approval and manages
the approval queue. It integrates with the Claude SDK's hook system
to intercept tool calls before execution.

Approval Rules (Default):
- Auto-approve: Read, Glob, Grep, WebSearch, WebFetch
- Require approval: Write, Edit, MultiEdit, Bash (configurable patterns)
- Pattern matching: Certain bash commands can be auto-approved
"""

from __future__ import annotations

import asyncio
import copy
import fnmatch
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.core.types import DiffStats, DiffTier, PendingApproval, RiskLevel
from src.utils.diff_generator import DiffResult, generate_diff

logger = logging.getLogger(__name__)


# Default timeout for approval wait (seconds). 0 = no timeout.
APPROVAL_TIMEOUT_SECONDS = 300  # 5 minutes


@dataclass
class ApprovalRule:
    """Defines an approval rule for a tool or pattern.

    Attributes:
        tool_name: Tool name to match (e.g., "Write", "Bash")
        auto_approve: If True, tool is auto-approved without user interaction
        patterns: For Bash commands, patterns that auto-approve (glob-style)
        description: Human-readable description of the rule
    """

    tool_name: str
    auto_approve: bool = False
    patterns: list[str] = field(default_factory=list)
    description: str = ""

    # Regex to split compound commands on shell operators.
    # Matches &&, ||, ;, and | (but not ||).
    _SHELL_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||[;|])\s*")

    def matches_pattern(self, command: str) -> bool:
        """Check if a command matches any auto-approve pattern.

        Compound commands (joined with &&, ||, ;, |) are split and
        EVERY segment must match a safe pattern. If any segment is
        unrecognized, the entire command requires approval.

        Args:
            command: The bash command to check

        Returns:
            True if command matches a pattern (safe to auto-approve)
        """
        if not self.patterns:
            return False

        # Split compound commands — every segment must be safe
        segments = self._SHELL_SPLIT_RE.split(command.strip())
        segments = [s.strip() for s in segments if s.strip()]

        if not segments:
            return False

        for segment in segments:
            if not self._matches_any_pattern(segment):
                return False

        return True

    def _matches_any_pattern(self, command: str) -> bool:
        """Check if a single command (no shell operators) matches a pattern."""
        for pattern in self.patterns:
            if fnmatch.fnmatch(command, pattern):
                return True
        return False


# Default approval rules
DEFAULT_RULES: dict[str, ApprovalRule] = {
    # Read-only tools - always auto-approve
    "Read": ApprovalRule(
        tool_name="Read",
        auto_approve=True,
        description="File reading is always safe",
    ),
    "Glob": ApprovalRule(
        tool_name="Glob",
        auto_approve=True,
        description="File pattern matching is always safe",
    ),
    "Grep": ApprovalRule(
        tool_name="Grep",
        auto_approve=True,
        description="File content searching is always safe",
    ),
    "WebSearch": ApprovalRule(
        tool_name="WebSearch",
        auto_approve=True,
        description="Web searching is always safe",
    ),
    "WebFetch": ApprovalRule(
        tool_name="WebFetch",
        auto_approve=True,
        description="Web fetching is always safe",
    ),
    # Write tools - require approval
    "Write": ApprovalRule(
        tool_name="Write",
        auto_approve=False,
        description="File writing requires approval",
    ),
    "Edit": ApprovalRule(
        tool_name="Edit",
        auto_approve=False,
        description="File editing requires approval",
    ),
    "MultiEdit": ApprovalRule(
        tool_name="MultiEdit",
        auto_approve=False,
        description="Multiple file editing requires approval",
    ),
    # Bash - requires approval with patterns for safe commands
    "Bash": ApprovalRule(
        tool_name="Bash",
        auto_approve=False,
        patterns=[
            "git status*",
            "git log*",
            "git diff*",
            "git branch*",
            "git show*",
            "ls*",
            "pwd",
            "cat *",
            "echo *",
            "head *",
            "tail *",
            "wc *",
            "which *",
            "type *",
            "npm list*",
            "npm outdated*",
            "npm view*",
            "pip list*",
            "pip show*",
            "python --version*",
            "node --version*",
        ],
        description="Bash commands require approval unless safe pattern matches",
    ),
}


@dataclass
class PendingApprovalRequest:
    """An approval request waiting for user decision.

    This is the in-memory representation of a pending approval,
    used to coordinate between the hook and the API.
    """

    session_id: str
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str
    file_path: str | None
    diff: str | None
    diff_stats: DiffStats | None
    risk_level: RiskLevel | None
    tier: DiffTier
    total_bytes: int
    total_lines: int
    requested_at: datetime
    event: asyncio.Event = field(default_factory=asyncio.Event)
    approved: bool | None = None
    feedback: str | None = None


class ApprovalHandler:
    """Handles tool approval workflow and decision processing.

    This class:
    - Determines which tools require approval based on rules
    - Queues pending approvals for user review
    - Processes approval/denial decisions
    - Provides hook integration for the SDK

    The handler maintains an in-memory queue of pending approvals
    coordinated with asyncio Events for the paused execution.
    """

    def __init__(
        self,
        rules: dict[str, ApprovalRule] | None = None,
        custom_patterns: list[str] | None = None,
    ) -> None:
        """Initialize the approval handler.

        Args:
            rules: Custom approval rules (uses defaults if None)
            custom_patterns: Additional bash patterns to auto-approve
        """
        self._rules = rules if rules is not None else copy.deepcopy(DEFAULT_RULES)
        self._pending: dict[str, PendingApprovalRequest] = {}
        self._lock = asyncio.Lock()

        # Add custom bash patterns if provided
        if custom_patterns:
            bash_rule = self._rules.get("Bash")
            if bash_rule:
                bash_rule.patterns.extend(custom_patterns)

    def requires_approval(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> bool:
        """Check if a tool use requires approval.

        Args:
            tool_name: Name of the tool (e.g., "Write", "Bash")
            tool_input: Input parameters to the tool

        Returns:
            True if user approval is required, False if auto-approved
        """
        rule = self._rules.get(tool_name)

        if rule is None:
            # Unknown tool - require approval by default
            logger.warning(f"Unknown tool '{tool_name}', requiring approval")
            return True

        if rule.auto_approve:
            return False

        # Check pattern matching for Bash commands
        if tool_name == "Bash" and rule.patterns:
            command = tool_input.get("command", "")
            if rule.matches_pattern(command):
                logger.debug(f"Bash command matches safe pattern: {command[:50]}...")
                return False

        return True

    def get_file_path(self, tool_name: str, tool_input: dict[str, Any]) -> str | None:
        """Extract the file path from tool input if applicable.

        Args:
            tool_name: Name of the tool
            tool_input: Tool input parameters

        Returns:
            File path or None if not applicable
        """
        if tool_name in ("Write", "Read", "Edit"):
            return tool_input.get("file_path") or tool_input.get("path")
        if tool_name == "MultiEdit":
            edits = tool_input.get("edits", [])
            if edits:
                return edits[0].get("file_path")
        return None

    def get_diff_result(
        self, tool_name: str, tool_input: dict[str, Any]
    ) -> DiffResult:
        """Generate diff, stats, and risk level for a tool operation.

        Uses the diff_generator module for proper unified diffs
        and bash risk assessment.

        Args:
            tool_name: Name of the tool
            tool_input: Tool input parameters

        Returns:
            DiffResult with all fields always present
        """
        return generate_diff(tool_name, tool_input)

    async def queue_approval(
        self,
        session_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
    ) -> PendingApprovalRequest:
        """Queue a tool use for approval.

        This creates a pending approval request and returns immediately.
        The caller should await the request's event to wait for the decision.

        Args:
            session_id: Our session ID
            tool_name: Name of the tool
            tool_input: Tool input parameters
            tool_use_id: SDK's tool use ID

        Returns:
            The PendingApprovalRequest with an event to await
        """
        diff_result = self.get_diff_result(tool_name, tool_input)

        request = PendingApprovalRequest(
            session_id=session_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_use_id=tool_use_id,
            file_path=self.get_file_path(tool_name, tool_input),
            diff=diff_result["diff"],
            diff_stats=diff_result["diff_stats"],
            risk_level=diff_result["risk_level"],
            tier=diff_result["tier"],
            total_bytes=diff_result["total_bytes"],
            total_lines=diff_result["total_lines"],
            requested_at=datetime.now(timezone.utc),
        )

        async with self._lock:
            existing = self._pending.get(session_id)
            if existing:
                logger.warning(
                    f"Overwriting existing pending approval for session {session_id}: "
                    f"was {existing.tool_name}, now {tool_name}"
                )
            self._pending[session_id] = request

        logger.info(
            f"Queued approval for session {session_id}: "
            f"{tool_name} (tool_use_id: {tool_use_id})"
        )

        return request

    async def get_pending(self, session_id: str) -> PendingApprovalRequest | None:
        """Get the pending approval for a session.

        Args:
            session_id: Our session ID

        Returns:
            The pending request or None
        """
        async with self._lock:
            return self._pending.get(session_id)

    async def process_decision(
        self,
        session_id: str,
        approved: bool,
        feedback: str | None = None,
    ) -> bool:
        """Process an approval/denial decision.

        This sets the decision on the pending request and signals
        the waiting event so execution can resume.

        Args:
            session_id: Our session ID
            approved: Whether the tool use was approved
            feedback: Optional feedback (especially for denials)

        Returns:
            True if a pending request was found and processed
        """
        async with self._lock:
            request = self._pending.get(session_id)
            if not request:
                logger.warning(f"No pending approval for session {session_id}")
                return False

            request.approved = approved
            request.feedback = feedback
            request.event.set()

            # Remove from pending
            del self._pending[session_id]

        action = "Approved" if approved else "Denied"
        logger.info(f"{action} tool use for session {session_id}")

        return True

    def to_pending_approval(
        self,
        request: PendingApprovalRequest,
    ) -> PendingApproval:
        """Convert a request to the storage format.

        Args:
            request: The pending approval request

        Returns:
            PendingApproval dict for database storage
        """
        return PendingApproval(
            tool_name=request.tool_name,
            tool_input=request.tool_input,
            tool_use_id=request.tool_use_id,
            file_path=request.file_path,
            diff=request.diff,
            diff_stats=request.diff_stats,
            risk_level=request.risk_level,
            diff_tier=request.tier,
            total_bytes=request.total_bytes,
            total_lines=request.total_lines,
            requested_at=request.requested_at.isoformat(),
        )

    async def clear_pending(self, session_id: str) -> None:
        """Clear any pending approval for a session.

        Signals the event as denied before removing, so any hook
        waiting on event.wait() unblocks immediately instead of
        hanging until the 300s timeout.

        Args:
            session_id: Our session ID
        """
        async with self._lock:
            request = self._pending.pop(session_id, None)
            if request:
                request.approved = False
                request.feedback = "Approval cleared (session cancelled)"
                request.event.set()


# Global approval handler instance (singleton pattern)
_approval_handler: ApprovalHandler | None = None
_handler_lock = asyncio.Lock()


async def get_approval_handler() -> ApprovalHandler:
    """Get or create the global approval handler.

    Returns:
        The global ApprovalHandler instance
    """
    global _approval_handler

    if _approval_handler is None:
        async with _handler_lock:
            if _approval_handler is None:
                _approval_handler = ApprovalHandler()

    return _approval_handler


def reset_approval_handler() -> None:
    """Reset the global approval handler (for testing)."""
    global _approval_handler
    _approval_handler = None
