"""Diff generation utilities for the approval workflow.

Generates unified diffs for file operations and risk assessments
for Bash commands. Used by ApprovalHandler to enrich pending
approval data sent to the frontend's DiffViewer component.

Two-tier model:
- inline (≤100KB): full diff stored and sent as-is
- truncated (>100KB): head+tail preview with omission marker
"""

from __future__ import annotations

import difflib
import os
import re
from typing import Any, TypedDict

from src.core.types import DiffStats, DiffTier, RiskLevel

# Inline threshold in bytes (~100KB). Diffs under this size are
# stored and sent in full. Above this, a head+tail preview is built.
INLINE_MAX_BYTES = 100_000

# Number of lines to show at the head/tail of a truncated diff preview.
PREVIEW_HEAD_LINES = 250
PREVIEW_TAIL_LINES = 250

# Number of bytes to scan for null bytes when detecting binary content.
_BINARY_CHECK_SIZE = 8192


class DiffResult(TypedDict):
    """Result of diff generation for a tool operation.

    All fields are always present — consumers don't need defensive .get().
    """

    diff: str | None
    diff_stats: DiffStats | None
    risk_level: RiskLevel | None
    tier: DiffTier
    total_bytes: int
    total_lines: int
    truncated: bool


# =============================================================================
# Bash Risk Patterns
# =============================================================================

# High risk: destructive, irreversible, or arbitrary code execution
_DANGEROUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+.*-[^\s]*r[^\s]*f"),  # rm -rf, rm -irf, etc.
    re.compile(r"\brm\s+.*-[^\s]*f[^\s]*r"),  # rm -fr
    re.compile(r"\bsudo\s+rm\b"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+"),
    re.compile(r">\s*/dev/"),
    re.compile(r"\|\s*sh\b"),
    re.compile(r"\|\s*bash\b"),
    re.compile(r"\bcurl\b.*\|\s*(sh|bash)\b"),
    re.compile(r"\bwget\b.*\|\s*(sh|bash)\b"),
    re.compile(r"\bchmod\s+777\b"),
    re.compile(r"\bchown\s+-R\b"),
    re.compile(r"\bgit\s+push\s+.*--force\b"),
    re.compile(r"\bgit\s+reset\s+--hard\b"),
    re.compile(r"\bgit\s+clean\s+-f"),
    re.compile(r":\(\)\s*\{"),  # fork bomb
    # Interpreter invocation (eval, sh -c, bash -c, env)
    re.compile(r"\beval\s+"),
    re.compile(r"\bsh\s+-c\b"),
    re.compile(r"\bbash\s+-c\b"),
]

# Medium risk: side effects, installs, network, process control
_MEDIUM_RISK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bgit\s+push\b"),
    re.compile(r"\bgit\s+checkout\s+\.\b"),
    re.compile(r"\bgit\s+stash\s+drop\b"),
    re.compile(r"\bpip\s+install\b"),
    re.compile(r"\bnpm\s+install\b"),
    re.compile(r"\byarn\s+add\b"),
    re.compile(r"\bcurl\b"),
    re.compile(r"\bwget\b"),
    re.compile(r"\bkill\b"),
    re.compile(r"\bpkill\b"),
    re.compile(r"\bmv\s+"),
    re.compile(r"\bcp\s+-r"),
    re.compile(r"\benv\s+\S"),  # env prefix to run commands
]

# Naive splitter for compound commands. Splits on ;, &&, ||
# outside of quotes. Intentionally over-splits (false positives
# are safer than false negatives in a security context).
_COMPOUND_SPLIT = re.compile(r"\s*(?:&&|\|\||;)\s*")


# =============================================================================
# Diff Generators
# =============================================================================


def generate_edit_diff(
    file_path: str,
    old_string: str,
    new_string: str,
) -> DiffResult:
    """Generate a unified diff for an Edit tool operation.

    Args:
        file_path: Path to the file being edited
        old_string: The text being replaced
        new_string: The replacement text

    Returns:
        DiffResult with unified diff, stats, and risk level
    """
    if _is_binary(old_string) or _is_binary(new_string):
        size = max(len(old_string.encode(errors="replace")),
                   len(new_string.encode(errors="replace")))
        return _binary_result(os.path.basename(file_path), size, "low")

    old_lines = old_string.splitlines(keepends=True)
    new_lines = new_string.splitlines(keepends=True)

    # Ensure last lines have newlines for clean diff output
    if old_lines and not old_lines[-1].endswith("\n"):
        old_lines[-1] += "\n"
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    filename = os.path.basename(file_path)
    diff_lines = list(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        n=3,
    ))

    return _finalize_diff(diff_lines, "low")


def generate_write_diff(
    file_path: str,
    content: str,
) -> DiffResult:
    """Generate a diff for a Write tool operation.

    Uses a/{filename} as the source since Write can overwrite existing
    files — we don't assume it's always a new file.

    Args:
        file_path: Path to the file being written
        content: The file content being written

    Returns:
        DiffResult with diff, stats, and risk level
    """
    if _is_binary(content):
        size = len(content.encode(errors="replace"))
        return _binary_result(os.path.basename(file_path), size, "low")

    filename = os.path.basename(file_path)
    new_lines = content.splitlines(keepends=True)
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    diff_lines = list(difflib.unified_diff(
        [],
        new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        n=0,
    ))

    return _finalize_diff(diff_lines, "low")


def generate_bash_diff(
    command: str,
) -> DiffResult:
    """Generate display info and risk assessment for a Bash command.

    Bash diffs are just the command text — no truncation concept.

    Args:
        command: The bash command to assess

    Returns:
        DiffResult with command as diff, no stats, and risk level
    """
    risk = assess_bash_risk(command)

    return DiffResult(
        diff=command,
        diff_stats=None,
        risk_level=risk,
        tier="inline",
        total_bytes=len(command.encode()),
        total_lines=command.count("\n") + 1,
        truncated=False,
    )


def assess_bash_risk(command: str) -> RiskLevel:
    """Assess the risk level of a bash command.

    Splits compound commands (;, &&, ||) and returns the highest
    risk found across all segments. Also checks the full command
    so cross-segment patterns (like piping to sh) are caught.

    Args:
        command: The bash command to assess

    Returns:
        "high", "medium", or "low"
    """
    # Check the full command first (catches cross-segment patterns
    # like "curl ... | sh" which span a pipe, not a compound operator)
    full_risk = _assess_single_command(command)
    if full_risk == "high":
        return "high"

    # Split on compound operators and check each segment
    segments = _COMPOUND_SPLIT.split(command)
    if len(segments) <= 1:
        return full_risk

    max_risk = full_risk
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        risk = _assess_single_command(segment)
        max_risk = _higher_risk(max_risk, risk)
        if max_risk == "high":
            return "high"

    return max_risk


def generate_diff(tool_name: str, tool_input: dict[str, Any]) -> DiffResult:
    """Generate a diff for any tool operation.

    This is the main entry point. Routes to the appropriate
    generator based on tool name.

    Args:
        tool_name: Name of the tool (Write, Edit, Bash, MultiEdit, etc.)
        tool_input: Tool input parameters

    Returns:
        DiffResult with diff, stats, and risk level
    """
    if tool_name == "Edit":
        file_path = tool_input.get("file_path", "unknown")
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")
        return generate_edit_diff(file_path, old_string, new_string)

    if tool_name == "Write":
        file_path = tool_input.get("file_path", "unknown")
        content = tool_input.get("content", "")
        return generate_write_diff(file_path, content)

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        return generate_bash_diff(command)

    if tool_name == "MultiEdit":
        return _generate_multiedit_diff(tool_input)

    # Unknown tool — no diff
    return DiffResult(
        diff=None, diff_stats=None, risk_level=None,
        tier="inline", total_bytes=0, total_lines=0, truncated=False,
    )


# =============================================================================
# Internal Helpers
# =============================================================================


def _generate_multiedit_diff(tool_input: dict[str, Any]) -> DiffResult:
    """Generate a combined diff for a MultiEdit tool operation.

    Collects raw diff lines from individual edits, then runs them
    through _finalize_diff for centralized truncation and metadata.
    """
    edits = tool_input.get("edits", [])
    if not edits:
        return DiffResult(
            diff=None, diff_stats=None, risk_level="low",
            tier="inline", total_bytes=0, total_lines=0, truncated=False,
        )

    all_diff_lines: list[str] = []
    total_add = 0
    total_del = 0

    for edit in edits:
        file_path = edit.get("file_path", "unknown")
        old_string = edit.get("old_string", "")
        new_string = edit.get("new_string", "")

        # Skip binary content in individual edits
        if _is_binary(old_string) or _is_binary(new_string):
            filename = os.path.basename(file_path)
            size = max(len(old_string.encode(errors="replace")),
                       len(new_string.encode(errors="replace")))
            all_diff_lines.append(f"Binary file {filename} ({_format_bytes(size)})\n")
            continue

        old_lines = old_string.splitlines(keepends=True)
        new_lines = new_string.splitlines(keepends=True)
        if old_lines and not old_lines[-1].endswith("\n"):
            old_lines[-1] += "\n"
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"

        filename = os.path.basename(file_path)
        diff_lines = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{filename}", tofile=f"b/{filename}",
            n=3,
        ))

        if diff_lines:
            all_diff_lines.extend(diff_lines)
            stats = _compute_stats(diff_lines)
            total_add += stats["additions"]
            total_del += stats["deletions"]

    if not all_diff_lines:
        return DiffResult(
            diff=None,
            diff_stats=DiffStats(additions=total_add, deletions=total_del),
            risk_level="low",
            tier="inline", total_bytes=0, total_lines=0, truncated=False,
        )

    # Finalize with centralized truncation
    result = _finalize_diff(all_diff_lines, "low")
    # Override stats with our accumulated totals (sub-diffs counted individually)
    result["diff_stats"] = DiffStats(additions=total_add, deletions=total_del)
    return result


def _finalize_diff(
    diff_lines: list[str],
    risk_level: RiskLevel,
) -> DiffResult:
    """Central exit point for all diff generators.

    Computes metadata from the full diff, then decides whether to
    return it inline or build a head+tail preview.
    """
    if not diff_lines:
        return DiffResult(
            diff=None,
            diff_stats=_compute_stats(diff_lines),
            risk_level=risk_level,
            tier="inline",
            total_bytes=0,
            total_lines=0,
            truncated=False,
        )

    full_text = "".join(diff_lines)
    total_bytes = len(full_text.encode())
    total_lines = full_text.count("\n")
    stats = _compute_stats(diff_lines)

    if total_bytes <= INLINE_MAX_BYTES:
        return DiffResult(
            diff=full_text,
            diff_stats=stats,
            risk_level=risk_level,
            tier="inline",
            total_bytes=total_bytes,
            total_lines=total_lines,
            truncated=False,
        )

    # Build head+tail preview
    preview = _build_preview(full_text, total_lines)
    return DiffResult(
        diff=preview,
        diff_stats=stats,
        risk_level=risk_level,
        tier="truncated",
        total_bytes=total_bytes,
        total_lines=total_lines,
        truncated=True,
    )


def _build_preview(diff_text: str, total_lines: int) -> str:
    """Build a head+tail preview from a large diff.

    Shows the first PREVIEW_HEAD_LINES and last PREVIEW_TAIL_LINES
    with an omission marker in between.
    """
    lines = diff_text.splitlines(keepends=True)
    head_n = PREVIEW_HEAD_LINES
    tail_n = PREVIEW_TAIL_LINES

    if len(lines) <= head_n + tail_n:
        # Shouldn't happen (byte threshold should exceed line threshold)
        # but handle gracefully
        return diff_text

    head = lines[:head_n]
    tail = lines[-tail_n:]
    omitted = len(lines) - head_n - tail_n

    return (
        "".join(head)
        + f"\n... ({omitted} lines omitted) ...\n\n"
        + "".join(tail)
    )


def _binary_result(
    filename: str,
    size: int,
    risk_level: RiskLevel,
) -> DiffResult:
    """Build a DiffResult for binary content."""
    msg = f"Binary file {filename} ({_format_bytes(size)})"
    return DiffResult(
        diff=msg,
        diff_stats=DiffStats(additions=0, deletions=0),
        risk_level=risk_level,
        tier="inline",
        total_bytes=size,
        total_lines=0,
        truncated=False,
    )


def _is_binary(content: str) -> bool:
    """Check if content is binary by looking for null bytes in the first 8KB."""
    return "\x00" in content[:_BINARY_CHECK_SIZE]


def _format_bytes(size: int) -> str:
    """Format byte size for human display."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _assess_single_command(command: str) -> RiskLevel:
    """Assess risk of a single (non-compound) command."""
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(command):
            return "high"

    for pattern in _MEDIUM_RISK_PATTERNS:
        if pattern.search(command):
            return "medium"

    return "low"


_RISK_ORDER: dict[RiskLevel, int] = {"low": 0, "medium": 1, "high": 2}


def _higher_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    """Return the higher of two risk levels."""
    return a if _RISK_ORDER[a] >= _RISK_ORDER[b] else b


def _compute_stats(diff_lines: list[str]) -> DiffStats:
    """Compute addition/deletion counts from unified diff lines."""
    additions = 0
    deletions = 0

    for line in diff_lines:
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1

    return DiffStats(additions=additions, deletions=deletions)
