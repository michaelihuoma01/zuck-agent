"""Filesystem browsing routes for the folder picker."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from src.api.deps import ApiKeyDep
from src.api.schemas import (
    DirectoryEntry,
    BreadcrumbEntry,
    DirectoryListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/filesystem", tags=["filesystem"])

# Browsing is restricted to the user's home directory subtree
HOME_DIR = Path.home()

# Project indicator files/dirs that hint "this is a project root"
PROJECT_INDICATORS = [
    ".git",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "CLAUDE.md",
    "Makefile",
    ".env",
    "requirements.txt",
    "pom.xml",
    "build.gradle",
]

# Shortcut directories shown at the home level
SHORTCUT_NAMES = ["Documents", "Desktop", "Downloads", "Developer", "Projects", "repos"]


def _is_safe_path(target: Path) -> bool:
    """Check that target is within the home directory subtree.

    Resolves symlinks before checking to prevent symlink escape attacks.
    """
    try:
        resolved = target.resolve()
        home_resolved = HOME_DIR.resolve()
        return resolved == home_resolved or str(resolved).startswith(str(home_resolved) + "/")
    except (OSError, ValueError):
        return False


def _detect_project_indicators(dir_path: Path) -> list[str]:
    """Check which project indicator files/dirs exist in a directory."""
    found = []
    for indicator in PROJECT_INDICATORS:
        if (dir_path / indicator).exists():
            found.append(indicator)
    return found


def _build_breadcrumbs(current_path: Path) -> list[BreadcrumbEntry]:
    """Build breadcrumb navigation from home to current path."""
    home_resolved = HOME_DIR.resolve()
    current_resolved = current_path.resolve()

    crumbs = [BreadcrumbEntry(name="~", path=str(home_resolved))]

    if current_resolved == home_resolved:
        return crumbs

    # Build relative path parts from home to current
    try:
        relative = current_resolved.relative_to(home_resolved)
    except ValueError:
        return crumbs

    accumulator = home_resolved
    for part in relative.parts:
        accumulator = accumulator / part
        crumbs.append(BreadcrumbEntry(name=part, path=str(accumulator)))

    return crumbs


@router.get(
    "/browse",
    response_model=DirectoryListResponse,
    summary="Browse directories for folder picker",
)
async def browse_directories(
    _api_key: ApiKeyDep,
    path: str | None = None,
) -> DirectoryListResponse:
    """List subdirectories of the given path for the folder picker.

    Defaults to the home directory. Only returns directories (never files).
    Hidden directories (starting with '.') are excluded.
    Restricted to the home directory subtree for security.
    """
    target = Path(path) if path else HOME_DIR

    if not _is_safe_path(target):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to home directory",
        )

    if not target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Directory not found: {target}",
        )

    resolved = target.resolve()

    # List subdirectories (skip hidden, skip files)
    entries: list[DirectoryEntry] = []
    try:
        for child in sorted(resolved.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith("."):
                continue

            # Check if this dir has its own subdirectories
            has_children = False
            try:
                has_children = any(
                    c.is_dir() and not c.name.startswith(".")
                    for c in child.iterdir()
                )
            except PermissionError:
                pass

            entries.append(
                DirectoryEntry(
                    name=child.name,
                    path=str(child),
                    has_children=has_children,
                    project_indicators=_detect_project_indicators(child),
                )
            )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {resolved}",
        )

    # Build shortcuts (only at home level)
    shortcuts: list[DirectoryEntry] = []
    if resolved == HOME_DIR.resolve():
        for name in SHORTCUT_NAMES:
            shortcut_path = resolved / name
            if shortcut_path.is_dir():
                shortcuts.append(
                    DirectoryEntry(
                        name=name,
                        path=str(shortcut_path),
                        has_children=True,
                    )
                )

    # Parent path (for back navigation, but not above home)
    parent_path: str | None = None
    if resolved != HOME_DIR.resolve():
        parent = resolved.parent
        if _is_safe_path(parent):
            parent_path = str(parent)

    return DirectoryListResponse(
        current_path=str(resolved),
        entries=entries,
        shortcuts=shortcuts,
        breadcrumbs=_build_breadcrumbs(resolved),
        parent_path=parent_path,
    )
