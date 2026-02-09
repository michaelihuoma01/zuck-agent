"""Tests for project API routes."""

import json
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from httpx import AsyncClient

from src.utils.session_discovery import encode_project_path, CLAUDE_PROJECTS_DIR
from src.services.preview_manager import PreviewStatus


class TestProjectAPI:
    """Tests for /projects endpoints."""

    async def test_list_projects_empty(self, api_client: AsyncClient):
        """GET /projects returns empty list initially."""
        response = await api_client.get("/projects")

        assert response.status_code == 200
        data = response.json()
        assert data["projects"] == []
        assert data["total"] == 0

    async def test_create_project(self, api_client: AsyncClient):
        """POST /projects creates a new project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_data = {
                "name": "Test Project",
                "path": tmpdir,
                "description": "A test project",
                "validate_path": True,
            }

            response = await api_client.post("/projects", json=project_data)

            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "Test Project"
            # macOS symlinks /var -> /private/var, so compare real paths
            assert os.path.realpath(data["path"]) == os.path.realpath(tmpdir)
            assert data["description"] == "A test project"
            assert "id" in data
            assert "created_at" in data
            assert "updated_at" in data

    async def test_create_project_skip_validation(self, api_client: AsyncClient):
        """POST /projects can skip path validation."""
        project_data = {
            "name": "Remote Project",
            "path": "/nonexistent/remote/path",
            "validate_path": False,
        }

        response = await api_client.post("/projects", json=project_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Remote Project"
        assert data["path"] == "/nonexistent/remote/path"

    async def test_create_project_invalid_path(self, api_client: AsyncClient):
        """POST /projects rejects invalid path when validation enabled."""
        project_data = {
            "name": "Bad Project",
            "path": "/definitely/not/a/real/path",
            "validate_path": True,
        }

        response = await api_client.post("/projects", json=project_data)

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    async def test_create_project_duplicate_path(self, api_client: AsyncClient):
        """POST /projects rejects duplicate path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_data = {
                "name": "First Project",
                "path": tmpdir,
                "validate_path": True,
            }

            # Create first project
            response = await api_client.post("/projects", json=project_data)
            assert response.status_code == 201

            # Try to create second with same path
            project_data["name"] = "Second Project"
            response = await api_client.post("/projects", json=project_data)

            assert response.status_code == 409
            data = response.json()
            assert "detail" in data

    async def test_list_projects_with_data(self, api_client: AsyncClient):
        """GET /projects returns created projects."""
        with tempfile.TemporaryDirectory() as tmpdir1, \
             tempfile.TemporaryDirectory() as tmpdir2:

            # Create two projects
            await api_client.post("/projects", json={
                "name": "Project A",
                "path": tmpdir1,
                "validate_path": True,
            })
            await api_client.post("/projects", json={
                "name": "Project B",
                "path": tmpdir2,
                "validate_path": True,
            })

            response = await api_client.get("/projects")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 2
            assert len(data["projects"]) == 2

            # Should be ordered by name
            names = [p["name"] for p in data["projects"]]
            assert "Project A" in names
            assert "Project B" in names

    async def test_get_project(self, api_client: AsyncClient):
        """GET /projects/{id} returns project details."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project
            create_response = await api_client.post("/projects", json={
                "name": "Test Project",
                "path": tmpdir,
                "validate_path": True,
            })
            project_id = create_response.json()["id"]

            # Get project
            response = await api_client.get(f"/projects/{project_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == project_id
            assert data["name"] == "Test Project"
            # macOS symlinks /var -> /private/var, so compare real paths
            assert os.path.realpath(data["path"]) == os.path.realpath(tmpdir)

    async def test_get_project_not_found(self, api_client: AsyncClient):
        """GET /projects/{id} returns 404 for unknown ID."""
        response = await api_client.get("/projects/nonexistent-id")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    async def test_update_project(self, api_client: AsyncClient):
        """PUT /projects/{id} updates project settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project
            create_response = await api_client.post("/projects", json={
                "name": "Original Name",
                "path": tmpdir,
                "validate_path": True,
            })
            project_id = create_response.json()["id"]

            # Update project
            response = await api_client.put(f"/projects/{project_id}", json={
                "name": "Updated Name",
                "description": "New description",
            })

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Updated Name"
            assert data["description"] == "New description"

    async def test_update_project_partial(self, api_client: AsyncClient):
        """PUT /projects/{id} allows partial updates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project with tools
            create_response = await api_client.post("/projects", json={
                "name": "Test Project",
                "path": tmpdir,
                "default_allowed_tools": ["Read", "Write"],
                "validate_path": True,
            })
            project_id = create_response.json()["id"]

            # Update only permission_mode
            response = await api_client.put(f"/projects/{project_id}", json={
                "permission_mode": "acceptEdits",
            })

            assert response.status_code == 200
            data = response.json()
            assert data["permission_mode"] == "acceptEdits"
            # Other fields should remain unchanged
            assert data["name"] == "Test Project"
            assert data["default_allowed_tools"] == ["Read", "Write"]

    async def test_update_project_not_found(self, api_client: AsyncClient):
        """PUT /projects/{id} returns 404 for unknown ID."""
        response = await api_client.put("/projects/nonexistent-id", json={
            "name": "New Name",
        })

        assert response.status_code == 404

    async def test_update_project_invalid_permission_mode(self, api_client: AsyncClient):
        """PUT /projects/{id} rejects invalid permission mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project
            create_response = await api_client.post("/projects", json={
                "name": "Test Project",
                "path": tmpdir,
                "validate_path": True,
            })
            project_id = create_response.json()["id"]

            # Try invalid permission mode
            response = await api_client.put(f"/projects/{project_id}", json={
                "permission_mode": "invalidMode",
            })

            assert response.status_code == 422  # Validation error

    async def test_delete_project(self, api_client: AsyncClient):
        """DELETE /projects/{id} removes a project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project
            create_response = await api_client.post("/projects", json={
                "name": "Test Project",
                "path": tmpdir,
                "validate_path": True,
            })
            project_id = create_response.json()["id"]

            # Delete project
            response = await api_client.delete(f"/projects/{project_id}")

            assert response.status_code == 204

            # Verify it's gone
            get_response = await api_client.get(f"/projects/{project_id}")
            assert get_response.status_code == 404

    async def test_delete_project_not_found(self, api_client: AsyncClient):
        """DELETE /projects/{id} returns 404 for unknown ID."""
        response = await api_client.delete("/projects/nonexistent-id")

        assert response.status_code == 404

    async def test_validate_project_path(self, api_client: AsyncClient):
        """GET /projects/{id}/validate checks path existence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project
            create_response = await api_client.post("/projects", json={
                "name": "Test Project",
                "path": tmpdir,
                "validate_path": True,
            })
            project_id = create_response.json()["id"]

            # Validate path (should exist)
            response = await api_client.get(f"/projects/{project_id}/validate")

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True

    async def test_validate_project_path_nonexistent(self, api_client: AsyncClient):
        """GET /projects/{id}/validate returns false for deleted path."""
        # Create project with validation skipped
        create_response = await api_client.post("/projects", json={
            "name": "Test Project",
            "path": "/nonexistent/path/here",
            "validate_path": False,
        })
        project_id = create_response.json()["id"]

        # Validate path (should not exist)
        response = await api_client.get(f"/projects/{project_id}/validate")

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    async def test_validate_project_path_not_found(self, api_client: AsyncClient):
        """GET /projects/{id}/validate returns 404 for unknown project."""
        response = await api_client.get("/projects/nonexistent-id/validate")

        assert response.status_code == 404


class TestExternalSessionDetail:
    """Tests for GET /projects/{id}/external-sessions/{session_id}."""

    async def _create_project_with_session(
        self, api_client: AsyncClient, session_entries: list[dict]
    ) -> tuple[str, str, str]:
        """Helper: create a project + write a JSONL file in the expected path.

        Returns (project_id, session_id, claude_dir).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project (skip path validation for temp dirs that may differ)
            resp = await api_client.post("/projects", json={
                "name": "ExtTest",
                "path": tmpdir,
                "validate_path": True,
            })
            assert resp.status_code == 201
            project_id = resp.json()["id"]

            # Use the stored path (realpath) to match what the API uses
            stored_path = resp.json()["path"]
            encoded = encode_project_path(stored_path)
            claude_dir = CLAUDE_PROJECTS_DIR / encoded
            claude_dir.mkdir(parents=True, exist_ok=True)

            session_id = "test-session-abc"
            jsonl_path = claude_dir / f"{session_id}.jsonl"
            with open(jsonl_path, "w") as f:
                for entry in session_entries:
                    f.write(json.dumps(entry) + "\n")

            yield project_id, session_id, str(claude_dir)

            # Cleanup
            if jsonl_path.exists():
                jsonl_path.unlink()
            if claude_dir.exists():
                try:
                    claude_dir.rmdir()
                except OSError:
                    pass

    async def test_get_external_session_messages(self, api_client: AsyncClient):
        """GET /external-sessions/{id} returns parsed messages."""
        entries = [
            {
                "type": "user",
                "uuid": "u1",
                "sessionId": "ses-xyz",
                "slug": "test-slug",
                "version": "1.0.0",
                "timestamp": "2025-01-01T10:00:00Z",
                "message": {"content": "Hello Claude"},
            },
            {
                "type": "assistant",
                "uuid": "a1",
                "sessionId": "ses-xyz",
                "timestamp": "2025-01-01T10:00:05Z",
                "message": {
                    "model": "claude-opus-4-6",
                    "content": [{"type": "text", "text": "Hello!"}],
                },
            },
        ]

        async for project_id, session_id, _ in self._create_project_with_session(
            api_client, entries
        ):
            resp = await api_client.get(
                f"/projects/{project_id}/external-sessions/{session_id}"
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["session_id"] == "ses-xyz"
            assert data["slug"] == "test-slug"
            assert data["model"] == "claude-opus-4-6"
            assert data["total_messages"] == 2
            assert data["messages"][0]["role"] == "user"
            assert data["messages"][0]["content"] == "Hello Claude"
            assert data["messages"][1]["role"] == "assistant"

    async def test_get_external_session_not_found(self, api_client: AsyncClient):
        """GET /external-sessions/{id} returns 404 for missing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resp = await api_client.post("/projects", json={
                "name": "NoSessions",
                "path": tmpdir,
                "validate_path": True,
            })
            project_id = resp.json()["id"]

            resp = await api_client.get(
                f"/projects/{project_id}/external-sessions/nonexistent"
            )

            assert resp.status_code == 404

    async def test_continue_external_session(self, api_client: AsyncClient):
        """POST /external-sessions/{id}/continue creates a ZURK session."""
        entries = [
            {
                "type": "user",
                "uuid": "u1",
                "sessionId": "ses-to-continue",
                "slug": "fix-bug",
                "timestamp": "2025-01-01T10:00:00Z",
                "message": {"content": "Fix the bug"},
            },
        ]

        async for project_id, session_id, _ in self._create_project_with_session(
            api_client, entries
        ):
            resp = await api_client.post(
                f"/projects/{project_id}/external-sessions/{session_id}/continue",
                json={"prompt": "Continue fixing the bug", "name": "Continued session"},
            )

            assert resp.status_code == 201
            data = resp.json()
            assert data["project_id"] == project_id
            assert data["claude_session_id"] == "ses-to-continue"
            assert data["name"] == "Continued session"
            assert data["last_prompt"] == "Continue fixing the bug"
            assert "id" in data  # ZURK session ID

    async def test_continue_nonexistent_session(self, api_client: AsyncClient):
        """POST /external-sessions/{id}/continue returns 404 for missing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resp = await api_client.post("/projects", json={
                "name": "NoSessions",
                "path": tmpdir,
                "validate_path": True,
            })
            project_id = resp.json()["id"]

            resp = await api_client.post(
                f"/projects/{project_id}/external-sessions/nonexistent/continue",
                json={"prompt": "Hello"},
            )

            assert resp.status_code == 404

    async def test_continue_requires_prompt(self, api_client: AsyncClient):
        """POST /external-sessions/{id}/continue rejects empty prompt."""
        entries = [
            {
                "type": "user",
                "sessionId": "ses-1",
                "timestamp": "T",
                "message": {"content": "Hi"},
            },
        ]

        async for project_id, session_id, _ in self._create_project_with_session(
            api_client, entries
        ):
            resp = await api_client.post(
                f"/projects/{project_id}/external-sessions/{session_id}/continue",
                json={"prompt": ""},
            )

            assert resp.status_code == 422  # Validation error (min_length=1)


# =============================================================================
# Preview API Tests
# =============================================================================


def _mock_preview_status(
    *,
    running: bool = True,
    url: str | None = "http://localhost:5173",
    port: int | None = 5173,
    pid: int | None = 12345,
    uptime_seconds: int | None = 10,
    project_type: str | None = "vite",
    error: str | None = None,
) -> PreviewStatus:
    """Helper to build a PreviewStatus for mocking."""
    return PreviewStatus(
        running=running,
        url=url,
        port=port,
        pid=pid,
        uptime_seconds=uptime_seconds,
        project_type=project_type,
        error=error,
    )


class TestPreviewAPI:
    """Tests for /projects/{id}/preview/* endpoints."""

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    async def _create_project(
        self,
        api_client: AsyncClient,
        *,
        dev_command: str | None = "npm run dev -- --host 0.0.0.0",
        dev_port: int | None = 5173,
    ) -> dict:
        """Create a project with optional dev_command/dev_port and return its JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "name": "Preview Test Project",
                "path": tmpdir,
                "validate_path": True,
                "dev_command": dev_command,
                "dev_port": dev_port,
            }
            resp = await api_client.post("/projects", json=data)
            assert resp.status_code == 201, resp.text
            return resp.json()

    # -----------------------------------------------------------------
    # POST /preview/start
    # -----------------------------------------------------------------

    async def test_start_preview_success(self, api_client: AsyncClient, monkeypatch):
        """POST /preview/start returns 200 with PreviewStatusResponse."""
        project = await self._create_project(api_client)
        project_id = project["id"]

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = PreviewStatus(running=False)
        mock_mgr.start_preview = AsyncMock(
            return_value=_mock_preview_status(running=True)
        )

        with patch(
            "src.api.routes.projects.get_preview_manager", return_value=mock_mgr
        ):
            resp = await api_client.post(f"/projects/{project_id}/preview/start")

        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True
        assert data["url"] == "http://localhost:5173"
        assert data["port"] == 5173
        assert data["pid"] == 12345

    async def test_start_preview_no_dev_command(self, api_client: AsyncClient, monkeypatch):
        """POST /preview/start returns 400 when project has no dev_command."""
        project = await self._create_project(
            api_client, dev_command=None, dev_port=None
        )
        project_id = project["id"]

        resp = await api_client.post(f"/projects/{project_id}/preview/start")

        assert resp.status_code == 400
        assert "dev_command" in resp.json()["detail"].lower()

    async def test_start_preview_already_running(self, api_client: AsyncClient, monkeypatch):
        """POST /preview/start returns 200 with error when preview is already running."""
        project = await self._create_project(api_client)
        project_id = project["id"]

        mock_mgr = MagicMock()
        mock_mgr.start_preview = AsyncMock(
            return_value=_mock_preview_status(
                running=True,
                error="Preview already running for this project",
            )
        )

        with patch(
            "src.api.routes.projects.get_preview_manager", return_value=mock_mgr
        ):
            resp = await api_client.post(f"/projects/{project_id}/preview/start")

        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True
        assert "already running" in data["error"].lower()

    async def test_start_preview_project_not_found(self, api_client: AsyncClient):
        """POST /preview/start returns 404 for unknown project."""
        resp = await api_client.post("/projects/nonexistent-id/preview/start")

        assert resp.status_code == 404

    # -----------------------------------------------------------------
    # POST /preview/stop
    # -----------------------------------------------------------------

    async def test_stop_preview_success(self, api_client: AsyncClient, monkeypatch):
        """POST /preview/stop returns 200 with running=False."""
        project = await self._create_project(api_client)
        project_id = project["id"]

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = _mock_preview_status(running=True)
        mock_mgr.stop_preview = AsyncMock(
            return_value=PreviewStatus(running=False)
        )

        with patch(
            "src.api.routes.projects.get_preview_manager", return_value=mock_mgr
        ):
            resp = await api_client.post(f"/projects/{project_id}/preview/stop")

        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is False

    async def test_stop_preview_not_running(self, api_client: AsyncClient, monkeypatch):
        """POST /preview/stop returns 404 when nothing is running."""
        project = await self._create_project(api_client)
        project_id = project["id"]

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = PreviewStatus(running=False)

        with patch(
            "src.api.routes.projects.get_preview_manager", return_value=mock_mgr
        ):
            resp = await api_client.post(f"/projects/{project_id}/preview/stop")

        assert resp.status_code == 404
        assert "no preview running" in resp.json()["detail"].lower()

    async def test_stop_preview_project_not_found(self, api_client: AsyncClient):
        """POST /preview/stop returns 404 for unknown project."""
        resp = await api_client.post("/projects/nonexistent-id/preview/stop")

        assert resp.status_code == 404

    # -----------------------------------------------------------------
    # GET /preview/status
    # -----------------------------------------------------------------

    async def test_get_preview_status_running(self, api_client: AsyncClient, monkeypatch):
        """GET /preview/status returns running status with URL."""
        project = await self._create_project(api_client)
        project_id = project["id"]

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = _mock_preview_status(running=True)

        with patch(
            "src.api.routes.projects.get_preview_manager", return_value=mock_mgr
        ):
            resp = await api_client.get(f"/projects/{project_id}/preview/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True
        assert data["url"] is not None
        assert data["port"] == 5173

    async def test_get_preview_status_not_running(self, api_client: AsyncClient, monkeypatch):
        """GET /preview/status returns running=False when nothing is active."""
        project = await self._create_project(api_client)
        project_id = project["id"]

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = PreviewStatus(running=False)

        with patch(
            "src.api.routes.projects.get_preview_manager", return_value=mock_mgr
        ):
            resp = await api_client.get(f"/projects/{project_id}/preview/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is False

    async def test_get_preview_status_project_not_found(self, api_client: AsyncClient):
        """GET /preview/status returns 404 for unknown project."""
        resp = await api_client.get("/projects/nonexistent-id/preview/status")

        assert resp.status_code == 404

    # -----------------------------------------------------------------
    # Project CRUD with dev_command / dev_port fields
    # -----------------------------------------------------------------

    async def test_create_project_with_dev_command(self, api_client: AsyncClient):
        """POST /projects with dev_command and dev_port stores them."""
        project = await self._create_project(
            api_client, dev_command="npm run dev", dev_port=3000
        )

        assert project["dev_command"] == "npm run dev"
        assert project["dev_port"] == 3000

    async def test_create_project_without_dev_command(self, api_client: AsyncClient):
        """POST /projects without dev_command still succeeds (fields nullable)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "name": "No Dev Project",
                "path": tmpdir,
                "validate_path": True,
            }
            resp = await api_client.post("/projects", json=data)

        assert resp.status_code == 201
        project = resp.json()
        # dev_command/dev_port may be auto-detected or null
        assert "dev_command" in project
        assert "dev_port" in project

    async def test_get_project_includes_dev_fields(self, api_client: AsyncClient):
        """GET /projects/{id} response includes dev_command and dev_port."""
        project = await self._create_project(
            api_client, dev_command="vite dev", dev_port=5173
        )

        resp = await api_client.get(f"/projects/{project['id']}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["dev_command"] == "vite dev"
        assert data["dev_port"] == 5173

    async def test_update_project_dev_command(self, api_client: AsyncClient):
        """PUT /projects/{id} can update dev_command and dev_port."""
        project = await self._create_project(
            api_client, dev_command="npm run dev", dev_port=3000
        )
        project_id = project["id"]

        resp = await api_client.put(f"/projects/{project_id}", json={
            "dev_command": "yarn dev --host",
            "dev_port": 4000,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["dev_command"] == "yarn dev --host"
        assert data["dev_port"] == 4000

    # -----------------------------------------------------------------
    # PreviewStatusResponse schema validation
    # -----------------------------------------------------------------

    async def test_preview_status_response_schema(self, api_client: AsyncClient, monkeypatch):
        """PreviewStatusResponse includes all expected fields."""
        project = await self._create_project(api_client)
        project_id = project["id"]

        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = _mock_preview_status(
            running=True,
            url="http://192.168.1.50:5173",
            port=5173,
            pid=99999,
            uptime_seconds=42,
            project_type="vite",
            error=None,
        )

        with patch(
            "src.api.routes.projects.get_preview_manager", return_value=mock_mgr
        ):
            resp = await api_client.get(f"/projects/{project_id}/preview/status")

        assert resp.status_code == 200
        data = resp.json()

        # All fields from PreviewStatusResponse should be present
        expected_fields = {
            "running", "url", "port", "pid",
            "uptime_seconds", "project_type", "error",
        }
        assert expected_fields.issubset(set(data.keys()))
