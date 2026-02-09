"""Tests for filesystem browsing API routes."""

import pytest
from pathlib import Path
from unittest.mock import patch
from httpx import AsyncClient

from src.api.routes.filesystem import _is_safe_path


class TestBrowseDirectories:
    """Tests for GET /filesystem/browse endpoint."""

    async def test_browse_home(self, api_client: AsyncClient, tmp_path: Path):
        """Browsing with no path returns home directory contents."""
        (tmp_path / "Documents").mkdir()
        (tmp_path / "projects").mkdir()

        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            response = await api_client.get("/filesystem/browse")

        assert response.status_code == 200
        data = response.json()
        assert data["current_path"] == str(tmp_path.resolve())
        names = [e["name"] for e in data["entries"]]
        assert "Documents" in names
        assert "projects" in names

    async def test_shortcuts_at_home(self, api_client: AsyncClient, tmp_path: Path):
        """Shortcuts are returned when browsing home level."""
        (tmp_path / "Documents").mkdir()
        (tmp_path / "Desktop").mkdir()

        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            response = await api_client.get("/filesystem/browse")

        data = response.json()
        shortcut_names = [s["name"] for s in data["shortcuts"]]
        assert "Documents" in shortcut_names
        assert "Desktop" in shortcut_names

    async def test_no_shortcuts_in_subdirectory(
        self, api_client: AsyncClient, tmp_path: Path
    ):
        """Shortcuts are NOT returned when browsing a subdirectory."""
        sub = tmp_path / "Documents"
        sub.mkdir()
        (sub / "project-a").mkdir()

        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            response = await api_client.get(
                f"/filesystem/browse?path={sub}"
            )

        data = response.json()
        assert data["shortcuts"] == []

    async def test_browse_specific_path(
        self, api_client: AsyncClient, tmp_path: Path
    ):
        """Browsing a specific path returns its subdirectories."""
        sub = tmp_path / "Documents"
        sub.mkdir()
        (sub / "my-project").mkdir()
        (sub / "other-project").mkdir()

        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            response = await api_client.get(
                f"/filesystem/browse?path={sub}"
            )

        assert response.status_code == 200
        data = response.json()
        names = [e["name"] for e in data["entries"]]
        assert "my-project" in names
        assert "other-project" in names

    async def test_outside_home_403(self, api_client: AsyncClient, tmp_path: Path):
        """Browsing outside home returns 403."""
        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            response = await api_client.get("/filesystem/browse?path=/etc")

        assert response.status_code == 403

    async def test_nonexistent_path_400(
        self, api_client: AsyncClient, tmp_path: Path
    ):
        """Browsing a nonexistent directory returns 400."""
        fake = tmp_path / "nonexistent"

        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            response = await api_client.get(
                f"/filesystem/browse?path={fake}"
            )

        assert response.status_code == 400

    async def test_hidden_dirs_excluded(
        self, api_client: AsyncClient, tmp_path: Path
    ):
        """Hidden directories (dot prefix) are excluded."""
        (tmp_path / "visible").mkdir()
        (tmp_path / ".hidden").mkdir()

        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            response = await api_client.get("/filesystem/browse")

        data = response.json()
        names = [e["name"] for e in data["entries"]]
        assert "visible" in names
        assert ".hidden" not in names

    async def test_files_excluded(self, api_client: AsyncClient, tmp_path: Path):
        """Regular files are never returned."""
        (tmp_path / "folder").mkdir()
        (tmp_path / "file.txt").write_text("hello")

        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            response = await api_client.get("/filesystem/browse")

        data = response.json()
        names = [e["name"] for e in data["entries"]]
        assert "folder" in names
        assert "file.txt" not in names

    async def test_project_indicators(
        self, api_client: AsyncClient, tmp_path: Path
    ):
        """Project indicators are detected."""
        project = tmp_path / "my-project"
        project.mkdir()
        (project / ".git").mkdir()
        (project / "package.json").write_text("{}")

        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            response = await api_client.get("/filesystem/browse")

        data = response.json()
        entry = next(e for e in data["entries"] if e["name"] == "my-project")
        assert ".git" in entry["project_indicators"]
        assert "package.json" in entry["project_indicators"]

    async def test_has_children_flag(
        self, api_client: AsyncClient, tmp_path: Path
    ):
        """has_children is true when directory has visible subdirectories."""
        parent = tmp_path / "parent"
        parent.mkdir()
        (parent / "child").mkdir()
        empty = tmp_path / "empty"
        empty.mkdir()

        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            response = await api_client.get("/filesystem/browse")

        data = response.json()
        parent_entry = next(e for e in data["entries"] if e["name"] == "parent")
        empty_entry = next(e for e in data["entries"] if e["name"] == "empty")
        assert parent_entry["has_children"] is True
        assert empty_entry["has_children"] is False

    async def test_breadcrumbs(self, api_client: AsyncClient, tmp_path: Path):
        """Breadcrumbs show path from home to current directory."""
        sub = tmp_path / "Documents" / "projects"
        sub.mkdir(parents=True)

        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            response = await api_client.get(
                f"/filesystem/browse?path={sub}"
            )

        data = response.json()
        crumb_names = [c["name"] for c in data["breadcrumbs"]]
        assert crumb_names[0] == "~"
        assert "Documents" in crumb_names
        assert "projects" in crumb_names

    async def test_parent_path(self, api_client: AsyncClient, tmp_path: Path):
        """parent_path is provided for non-home directories."""
        sub = tmp_path / "Documents"
        sub.mkdir()

        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            # At home — no parent
            response = await api_client.get("/filesystem/browse")
            assert response.json()["parent_path"] is None

            # In subdirectory — parent is home
            response = await api_client.get(
                f"/filesystem/browse?path={sub}"
            )
            assert response.json()["parent_path"] == str(tmp_path.resolve())


class TestFilesystemSecurity:
    """Direct tests for _is_safe_path helper."""

    def test_home_is_safe(self, tmp_path: Path):
        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            assert _is_safe_path(tmp_path) is True

    def test_subdirectory_is_safe(self, tmp_path: Path):
        sub = tmp_path / "Documents"
        sub.mkdir()
        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            assert _is_safe_path(sub) is True

    def test_outside_home_is_unsafe(self, tmp_path: Path):
        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            assert _is_safe_path(Path("/etc")) is False

    def test_traversal_attack(self, tmp_path: Path):
        with patch("src.api.routes.filesystem.HOME_DIR", tmp_path):
            assert _is_safe_path(tmp_path / ".." / "..") is False
