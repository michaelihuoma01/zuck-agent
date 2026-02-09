"""Project Registry - Manage registered project directories."""

from pathlib import Path
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Project
from src.core.exceptions import (
    ProjectNotFoundError,
    ProjectPathExistsError,
    ProjectPathInvalidError,
    ProjectValidationError,
)
from src.core.constants import DESCRIPTION_MAX_LENGTH
from src.utils.project_detector import detect_project_type

# Valid permission modes for projects
VALID_PERMISSION_MODES = frozenset({"default", "acceptEdits", "manual"})


class ProjectRegistry:
    """Manages registered project directories and their configurations.

    Responsibilities:
    - Register project paths with names and descriptions
    - Auto-detect existing Claude Code configuration
    - Store default tool permissions per project
    - Validate project paths exist and are accessible
    """

    def __init__(self, db: AsyncSession):
        """Initialize with database session.

        Args:
            db: Async SQLAlchemy session
        """
        self.db = db

    async def register_project(
        self,
        name: str,
        path: str,
        description: str | None = None,
        default_allowed_tools: list[str] | None = None,
        permission_mode: str = "default",
        auto_approve_patterns: list[str] | None = None,
        validate_path: bool = True,
        dev_command: str | None = None,
        dev_port: int | None = None,
    ) -> Project:
        """Register a new project directory.

        Args:
            name: Display name for the project
            path: Absolute path to project directory
            description: Optional description
            default_allowed_tools: Tools enabled by default
            permission_mode: One of "default", "acceptEdits", "manual"
            auto_approve_patterns: Bash patterns to auto-approve
            validate_path: Whether to validate the path exists

        Returns:
            The created Project

        Raises:
            ProjectPathExistsError: If path is already registered
            ProjectPathInvalidError: If path doesn't exist (when validate_path=True)
        """
        # Validate permission_mode
        if permission_mode not in VALID_PERMISSION_MODES:
            raise ProjectValidationError(
                f"Invalid permission_mode: {permission_mode}. "
                f"Must be one of: {', '.join(sorted(VALID_PERMISSION_MODES))}"
            )

        # Normalize and validate path
        project_path = Path(path).resolve()

        if validate_path:
            if not project_path.exists():
                raise ProjectPathInvalidError(f"Path does not exist: {project_path}")
            if not project_path.is_dir():
                raise ProjectPathInvalidError(f"Path is not a directory: {project_path}")

        path_str = str(project_path)

        # Check for duplicate path
        existing = await self.db.execute(
            select(Project).where(Project.path == path_str)
        )
        if existing.scalar_one_or_none():
            raise ProjectPathExistsError(f"Project already registered at: {path_str}")

        # Auto-detect Claude Code configuration
        detected_config = self._detect_claude_config(project_path)

        # Auto-detect dev server command/port if not provided
        if dev_command is None or dev_port is None:
            detected_cmd, detected_port, _ = detect_project_type(path_str)
            if dev_command is None:
                dev_command = detected_cmd
            if dev_port is None:
                dev_port = detected_port

        # Create project with auto-detected values as defaults
        project = Project(
            name=name,
            path=path_str,
            description=description or detected_config.get("description"),
            default_allowed_tools=default_allowed_tools or [],
            permission_mode=permission_mode,
            auto_approve_patterns=auto_approve_patterns or [],
            dev_command=dev_command,
            dev_port=dev_port,
        )

        self.db.add(project)
        await self.db.commit()
        await self.db.refresh(project)

        return project

    async def list_projects(self) -> Sequence[Project]:
        """List all registered projects.

        Returns:
            List of all projects, ordered by name
        """
        result = await self.db.execute(
            select(Project).order_by(Project.name)
        )
        return result.scalars().all()

    async def get_project(self, project_id: str) -> Project:
        """Get a project by ID.

        Args:
            project_id: The project's UUID

        Returns:
            The Project

        Raises:
            ProjectNotFoundError: If project doesn't exist
        """
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()

        if not project:
            raise ProjectNotFoundError(f"Project not found: {project_id}")

        return project

    async def get_project_by_path(self, path: str) -> Project | None:
        """Get a project by its path.

        Args:
            path: The project path

        Returns:
            The Project or None if not found
        """
        normalized_path = str(Path(path).resolve())
        result = await self.db.execute(
            select(Project).where(Project.path == normalized_path)
        )
        return result.scalar_one_or_none()

    async def update_project(
        self,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
        default_allowed_tools: list[str] | None = None,
        permission_mode: str | None = None,
        auto_approve_patterns: list[str] | None = None,
        dev_command: str | None = None,
        dev_port: int | None = None,
    ) -> Project:
        """Update a project's settings.

        Args:
            project_id: The project's UUID
            name: New display name (optional)
            description: New description (optional)
            default_allowed_tools: New tool list (optional)
            permission_mode: New permission mode (optional)
            auto_approve_patterns: New patterns (optional)

        Returns:
            The updated Project

        Raises:
            ProjectNotFoundError: If project doesn't exist
        """
        project = await self.get_project(project_id)

        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        if default_allowed_tools is not None:
            project.default_allowed_tools = default_allowed_tools
        if permission_mode is not None:
            if permission_mode not in VALID_PERMISSION_MODES:
                raise ProjectValidationError(
                    f"Invalid permission_mode: {permission_mode}. "
                    f"Must be one of: {', '.join(sorted(VALID_PERMISSION_MODES))}"
                )
            project.permission_mode = permission_mode
        if auto_approve_patterns is not None:
            project.auto_approve_patterns = auto_approve_patterns
        if dev_command is not None:
            project.dev_command = dev_command
        if dev_port is not None:
            project.dev_port = dev_port

        await self.db.commit()
        await self.db.refresh(project)

        return project

    async def delete_project(self, project_id: str) -> None:
        """Delete a project (and all its sessions via cascade).

        Args:
            project_id: The project's UUID

        Raises:
            ProjectNotFoundError: If project doesn't exist
        """
        project = await self.get_project(project_id)
        await self.db.delete(project)
        await self.db.commit()

    def _detect_claude_config(self, project_path: Path) -> dict:
        """Auto-detect Claude Code configuration in a project.

        Looks for:
        - .claude/ directory
        - CLAUDE.md file

        Args:
            project_path: Path to project directory

        Returns:
            Dict with detected configuration
        """
        config = {}

        # Check for .claude directory
        claude_dir = project_path / ".claude"
        if claude_dir.exists() and claude_dir.is_dir():
            config["has_claude_dir"] = True

        # Check for CLAUDE.md and try to extract description
        claude_md = project_path / "CLAUDE.md"
        if claude_md.exists() and claude_md.is_file():
            config["has_claude_md"] = True
            try:
                content = claude_md.read_text(encoding="utf-8")
                # Try to extract first paragraph as description
                lines = content.strip().split("\n")
                for line in lines:
                    line = line.strip()
                    # Skip headers and empty lines
                    if line and not line.startswith("#") and not line.startswith(">"):
                        config["description"] = line[:DESCRIPTION_MAX_LENGTH]
                        break
            except Exception:
                pass  # Ignore read errors

        return config

    async def validate_project_path(self, project_id: str) -> bool:
        """Check if a project's path still exists and is accessible.

        Args:
            project_id: The project's UUID

        Returns:
            True if path is valid, False otherwise

        Raises:
            ProjectNotFoundError: If project doesn't exist
        """
        project = await self.get_project(project_id)
        path = Path(project.path)
        return path.exists() and path.is_dir()
