"""Tests for ProjectRegistry."""

import pytest
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import (
    ProjectRegistry,
    ProjectNotFoundError,
    ProjectPathExistsError,
    ProjectPathInvalidError,
    ProjectValidationError,
)
from src.models import Project


class TestProjectRegistry:
    """Tests for the ProjectRegistry class."""

    async def test_register_project(self, db_session: AsyncSession, tmp_path: Path):
        """Test registering a new project."""
        registry = ProjectRegistry(db_session)

        project = await registry.register_project(
            name="Test Project",
            path=str(tmp_path),
            description="A test project",
            default_allowed_tools=["Read", "Write"],
            permission_mode="default",
            auto_approve_patterns=["git status"],
        )

        assert project.id is not None
        assert project.name == "Test Project"
        assert project.path == str(tmp_path)
        assert project.description == "A test project"
        assert project.default_allowed_tools == ["Read", "Write"]
        assert project.permission_mode == "default"
        assert project.auto_approve_patterns == ["git status"]

    async def test_register_project_validates_path(self, db_session: AsyncSession):
        """Test that registering with invalid path raises error."""
        registry = ProjectRegistry(db_session)

        with pytest.raises(ProjectPathInvalidError, match="does not exist"):
            await registry.register_project(
                name="Invalid Project",
                path="/nonexistent/path/xyz123",
            )

    async def test_register_project_skip_validation(self, db_session: AsyncSession):
        """Test registering with validation disabled."""
        registry = ProjectRegistry(db_session)

        project = await registry.register_project(
            name="No Validation Project",
            path="/fake/path/for/testing",
            validate_path=False,
        )

        assert project.id is not None
        assert project.path == "/fake/path/for/testing"

    async def test_register_project_duplicate_path(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        """Test that registering duplicate path raises error."""
        registry = ProjectRegistry(db_session)

        await registry.register_project(
            name="First Project",
            path=str(tmp_path),
        )

        with pytest.raises(ProjectPathExistsError, match="already registered"):
            await registry.register_project(
                name="Second Project",
                path=str(tmp_path),
            )

    async def test_list_projects(self, db_session: AsyncSession, tmp_path: Path):
        """Test listing all projects."""
        registry = ProjectRegistry(db_session)

        # Create multiple projects
        for name in ["Zebra", "Alpha", "Beta"]:
            project_path = tmp_path / name.lower()
            project_path.mkdir()
            await registry.register_project(name=name, path=str(project_path))

        projects = await registry.list_projects()

        assert len(projects) == 3
        # Should be ordered by name
        assert [p.name for p in projects] == ["Alpha", "Beta", "Zebra"]

    async def test_get_project(self, db_session: AsyncSession, tmp_path: Path):
        """Test getting a project by ID."""
        registry = ProjectRegistry(db_session)

        created = await registry.register_project(
            name="Get Test",
            path=str(tmp_path),
        )

        fetched = await registry.get_project(created.id)

        assert fetched.id == created.id
        assert fetched.name == "Get Test"

    async def test_get_project_not_found(self, db_session: AsyncSession):
        """Test getting a nonexistent project raises error."""
        registry = ProjectRegistry(db_session)

        with pytest.raises(ProjectNotFoundError, match="not found"):
            await registry.get_project("nonexistent-uuid")

    async def test_get_project_by_path(self, db_session: AsyncSession, tmp_path: Path):
        """Test getting a project by its path."""
        registry = ProjectRegistry(db_session)

        created = await registry.register_project(
            name="Path Test",
            path=str(tmp_path),
        )

        fetched = await registry.get_project_by_path(str(tmp_path))

        assert fetched is not None
        assert fetched.id == created.id

    async def test_get_project_by_path_not_found(self, db_session: AsyncSession):
        """Test getting by nonexistent path returns None."""
        registry = ProjectRegistry(db_session)

        result = await registry.get_project_by_path("/nonexistent/path")
        assert result is None

    async def test_update_project(self, db_session: AsyncSession, tmp_path: Path):
        """Test updating a project."""
        registry = ProjectRegistry(db_session)

        project = await registry.register_project(
            name="Original Name",
            path=str(tmp_path),
            permission_mode="default",
        )

        updated = await registry.update_project(
            project.id,
            name="New Name",
            description="New description",
            permission_mode="acceptEdits",
            default_allowed_tools=["Bash"],
            auto_approve_patterns=["npm test"],
        )

        assert updated.name == "New Name"
        assert updated.description == "New description"
        assert updated.permission_mode == "acceptEdits"
        assert updated.default_allowed_tools == ["Bash"]
        assert updated.auto_approve_patterns == ["npm test"]

    async def test_update_project_partial(self, db_session: AsyncSession, tmp_path: Path):
        """Test partial update only changes specified fields."""
        registry = ProjectRegistry(db_session)

        project = await registry.register_project(
            name="Original",
            path=str(tmp_path),
            description="Original desc",
        )

        updated = await registry.update_project(project.id, name="Updated")

        assert updated.name == "Updated"
        assert updated.description == "Original desc"  # Unchanged

    async def test_update_project_invalid_permission_mode(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        """Test updating with invalid permission_mode raises error."""
        registry = ProjectRegistry(db_session)

        project = await registry.register_project(
            name="Test",
            path=str(tmp_path),
        )

        with pytest.raises(ProjectValidationError, match="Invalid permission_mode"):
            await registry.update_project(project.id, permission_mode="invalid")

    async def test_register_project_invalid_permission_mode(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        """Test registering with invalid permission_mode raises error."""
        registry = ProjectRegistry(db_session)

        with pytest.raises(ProjectValidationError, match="Invalid permission_mode"):
            await registry.register_project(
                name="Test",
                path=str(tmp_path),
                permission_mode="invalid_mode",
            )

    async def test_delete_project(self, db_session: AsyncSession, tmp_path: Path):
        """Test deleting a project."""
        registry = ProjectRegistry(db_session)

        project = await registry.register_project(
            name="To Delete",
            path=str(tmp_path),
        )
        project_id = project.id

        await registry.delete_project(project_id)

        with pytest.raises(ProjectNotFoundError):
            await registry.get_project(project_id)

    async def test_delete_project_not_found(self, db_session: AsyncSession):
        """Test deleting a nonexistent project raises error."""
        registry = ProjectRegistry(db_session)

        with pytest.raises(ProjectNotFoundError):
            await registry.delete_project("nonexistent-uuid")

    async def test_detect_claude_config(self, db_session: AsyncSession, tmp_path: Path):
        """Test auto-detection of Claude configuration."""
        registry = ProjectRegistry(db_session)

        # Create .claude directory
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        # Create CLAUDE.md with content
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Project Title\n\nThis is the project description.\n")

        project = await registry.register_project(
            name="Config Test",
            path=str(tmp_path),
        )

        # Description should be auto-detected from CLAUDE.md
        assert project.description == "This is the project description."

    async def test_validate_project_path(self, db_session: AsyncSession, tmp_path: Path):
        """Test validating a project's path still exists."""
        registry = ProjectRegistry(db_session)

        project = await registry.register_project(
            name="Validate Test",
            path=str(tmp_path),
        )

        assert await registry.validate_project_path(project.id) is True

    async def test_validate_project_path_deleted(
        self, db_session: AsyncSession, tmp_path: Path
    ):
        """Test validating a project with deleted path returns False."""
        registry = ProjectRegistry(db_session)

        # Create a subdirectory that we'll delete
        project_dir = tmp_path / "to_delete"
        project_dir.mkdir()

        project = await registry.register_project(
            name="Validate Test",
            path=str(project_dir),
        )

        # Delete the directory
        project_dir.rmdir()

        assert await registry.validate_project_path(project.id) is False
