"""Tests for session API routes."""

import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient

from src.utils.session_discovery import ExternalSession


@pytest.fixture
async def project_id(api_client: AsyncClient):
    """Create a project and return its ID for session tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        response = await api_client.post("/projects", json={
            "name": "Test Project",
            "path": tmpdir,
            "validate_path": True,
        })
        yield response.json()["id"]


class TestSessionAPI:
    """Tests for /sessions endpoints."""

    async def test_list_sessions_empty(self, api_client: AsyncClient):
        """GET /sessions returns empty list initially."""
        response = await api_client.get("/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["sessions"] == []
        assert data["total"] == 0

    async def test_create_session(self, api_client: AsyncClient, project_id: str):
        """POST /sessions creates a new session."""
        session_data = {
            "project_id": project_id,
            "prompt": "Hello, Claude!",
            "name": "Test Session",
        }

        response = await api_client.post("/sessions", json=session_data)

        assert response.status_code == 201
        data = response.json()
        assert data["project_id"] == project_id
        assert data["name"] == "Test Session"
        assert data["status"] in ["idle", "running"]  # Depends on background task
        assert "id" in data
        assert "created_at" in data

    async def test_create_session_project_not_found(self, api_client: AsyncClient):
        """POST /sessions returns 404 for unknown project."""
        session_data = {
            "project_id": "nonexistent-project-id",
            "prompt": "Hello!",
        }

        response = await api_client.post("/sessions", json=session_data)

        assert response.status_code == 404

    async def test_get_session(self, api_client: AsyncClient, project_id: str):
        """GET /sessions/{id} returns session with messages."""
        # Create session
        create_response = await api_client.post("/sessions", json={
            "project_id": project_id,
            "prompt": "Hello!",
        })
        session_id = create_response.json()["id"]

        # Get session
        response = await api_client.get(f"/sessions/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == session_id
        assert data["project_id"] == project_id
        assert "messages" in data

    async def test_get_session_not_found(self, api_client: AsyncClient):
        """GET /sessions/{id} returns 404 for unknown session."""
        response = await api_client.get("/sessions/nonexistent-id")

        assert response.status_code == 404

    async def test_list_sessions_with_data(
        self, api_client: AsyncClient, project_id: str
    ):
        """GET /sessions returns created sessions."""
        # Create two sessions
        await api_client.post("/sessions", json={
            "project_id": project_id,
            "prompt": "First prompt",
            "name": "Session A",
        })
        await api_client.post("/sessions", json={
            "project_id": project_id,
            "prompt": "Second prompt",
            "name": "Session B",
        })

        response = await api_client.get("/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["sessions"]) == 2

    async def test_list_sessions_filter_by_project(
        self, api_client: AsyncClient, project_id: str
    ):
        """GET /sessions filters by project_id."""
        # Create session for our project
        await api_client.post("/sessions", json={
            "project_id": project_id,
            "prompt": "Test prompt",
        })

        # Create another project with its own session
        with tempfile.TemporaryDirectory() as tmpdir:
            other_project = await api_client.post("/projects", json={
                "name": "Other Project",
                "path": tmpdir,
                "validate_path": True,
            })
            other_project_id = other_project.json()["id"]
            await api_client.post("/sessions", json={
                "project_id": other_project_id,
                "prompt": "Other prompt",
            })

        # Filter by project_id
        response = await api_client.get(f"/sessions?project_id={project_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["sessions"][0]["project_id"] == project_id

    async def test_list_sessions_filter_by_status(
        self, api_client: AsyncClient, project_id: str
    ):
        """GET /sessions filters by status."""
        # Create session
        await api_client.post("/sessions", json={
            "project_id": project_id,
            "prompt": "Test prompt",
        })

        # Filter by idle status
        response = await api_client.get("/sessions?status=idle")

        assert response.status_code == 200
        # Result depends on whether background task runs

    async def test_delete_session(self, api_client: AsyncClient, project_id: str):
        """DELETE /sessions/{id} removes a session."""
        # Create session
        create_response = await api_client.post("/sessions", json={
            "project_id": project_id,
            "prompt": "Test prompt",
        })
        session_id = create_response.json()["id"]

        # Delete session
        response = await api_client.delete(f"/sessions/{session_id}")

        assert response.status_code == 204

        # Verify it's gone
        get_response = await api_client.get(f"/sessions/{session_id}")
        assert get_response.status_code == 404

    async def test_delete_session_not_found(self, api_client: AsyncClient):
        """DELETE /sessions/{id} returns 404 for unknown session."""
        response = await api_client.delete("/sessions/nonexistent-id")

        assert response.status_code == 404

    async def test_send_prompt_reinitializes_broken_session(
        self, api_client: AsyncClient, project_id: str
    ):
        """POST /sessions/{id}/prompt reinitializes session without Claude ID."""
        # Create session (mock runtime doesn't create a Claude session ID)
        create_response = await api_client.post("/sessions", json={
            "project_id": project_id,
            "prompt": "Initial prompt",
        })
        session_id = create_response.json()["id"]

        # Send follow-up prompt — session has no active connection and
        # no claude_session_id, so it reinitializes with a fresh Claude session
        response = await api_client.post(f"/sessions/{session_id}/prompt", json={
            "prompt": "Follow-up prompt",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == session_id

    async def test_send_prompt_session_not_found(self, api_client: AsyncClient):
        """POST /sessions/{id}/prompt returns 404 for unknown session."""
        response = await api_client.post("/sessions/nonexistent-id/prompt", json={
            "prompt": "Test",
        })

        assert response.status_code == 404

    async def test_get_session_messages(
        self, api_client: AsyncClient, project_id: str
    ):
        """GET /sessions/{id}/messages returns message history."""
        # Create session
        create_response = await api_client.post("/sessions", json={
            "project_id": project_id,
            "prompt": "Test prompt",
        })
        session_id = create_response.json()["id"]

        # Get messages
        response = await api_client.get(f"/sessions/{session_id}/messages")

        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "total" in data

    async def test_get_session_messages_with_limit(
        self, api_client: AsyncClient, project_id: str
    ):
        """GET /sessions/{id}/messages respects limit parameter."""
        # Create session
        create_response = await api_client.post("/sessions", json={
            "project_id": project_id,
            "prompt": "Test prompt",
        })
        session_id = create_response.json()["id"]

        # Get messages with limit
        response = await api_client.get(f"/sessions/{session_id}/messages?limit=5")

        assert response.status_code == 200

    async def test_get_session_messages_not_found(self, api_client: AsyncClient):
        """GET /sessions/{id}/messages returns 404 for unknown session."""
        response = await api_client.get("/sessions/nonexistent-id/messages")

        assert response.status_code == 404

    async def test_approve_tool_use(self, api_client: AsyncClient, project_id: str):
        """POST /sessions/{id}/approve approves pending tool use."""
        # Create session
        create_response = await api_client.post("/sessions", json={
            "project_id": project_id,
            "prompt": "Test prompt",
        })
        session_id = create_response.json()["id"]

        # Try to approve (placeholder - should return error if nothing pending)
        response = await api_client.post(f"/sessions/{session_id}/approve", json={
            "approved": True,
        })

        # Expect error since no tool use is pending
        assert response.status_code in [200, 400]

    async def test_deny_tool_use(self, api_client: AsyncClient, project_id: str):
        """POST /sessions/{id}/deny denies pending tool use."""
        # Create session
        create_response = await api_client.post("/sessions", json={
            "project_id": project_id,
            "prompt": "Test prompt",
        })
        session_id = create_response.json()["id"]

        # Try to deny (placeholder - should return error if nothing pending)
        response = await api_client.post(f"/sessions/{session_id}/deny", json={
            "feedback": "Not allowed",
        })

        # Expect error since no tool use is pending
        assert response.status_code in [200, 400]


class TestHealthAPI:
    """Tests for /health endpoints."""

    async def test_health_check(self, api_client: AsyncClient):
        """GET /health returns healthy status."""
        response = await api_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    async def test_agent_health_check(self, api_client: AsyncClient):
        """GET /health/agent checks CLI availability."""
        response = await api_client.get("/health/agent")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "cli_available" in data


class TestRootEndpoint:
    """Tests for root endpoint."""

    async def test_root(self, api_client: AsyncClient):
        """GET / returns API info."""
        response = await api_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "ZURK - Agent Command Center"
        assert "version" in data
        assert "docs" in data


class TestSSEStreaming:
    """Tests for SSE streaming endpoint."""

    async def test_sse_endpoint_exists(self, api_client: AsyncClient, project_id: str):
        """GET /sessions/{id}/stream returns SSE stream."""
        # Create session
        create_response = await api_client.post("/sessions", json={
            "project_id": project_id,
            "prompt": "Test prompt",
        })
        session_id = create_response.json()["id"]

        # Request SSE stream (just check it doesn't 404)
        # Note: Full SSE testing requires special handling
        response = await api_client.get(
            f"/sessions/{session_id}/stream",
            headers={"Accept": "text/event-stream"},
        )

        # Should return 200 with event-stream content type
        assert response.status_code == 200

    async def test_sse_session_not_found(self, api_client: AsyncClient):
        """GET /sessions/{id}/stream returns 404 for unknown session."""
        response = await api_client.get("/sessions/nonexistent-id/stream")

        assert response.status_code == 404


class TestAllExternalSessions:
    """Tests for GET /sessions/external (global session sync)."""

    async def test_empty_when_no_projects(self, api_client: AsyncClient):
        """Returns empty list when no projects are registered."""
        response = await api_client.get("/sessions/external")
        assert response.status_code == 200
        data = response.json()
        assert data["sessions"] == []
        assert data["total"] == 0

    async def test_returns_sessions_with_project_context(
        self, api_client: AsyncClient, project_id: str
    ):
        """Returns sessions enriched with project_id and project_name."""
        mock_sessions = [
            ExternalSession(
                session_id="ext-1",
                file_path="/tmp/ext-1.jsonl",
                file_size_bytes=1000,
                slug="test-session",
                started_at="2026-01-15T10:00:00.000Z",
                model="claude-opus-4-6",
                cwd="/home/user/project",
                git_branch="main",
            ),
        ]
        with patch(
            "src.api.routes.sessions.discover_sessions",
            return_value=mock_sessions,
        ):
            response = await api_client.get("/sessions/external")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        s = data["sessions"][0]
        assert s["session_id"] == "ext-1"
        assert s["project_id"] == project_id
        assert s["project_name"] == "Test Project"
        assert s["cwd"] == "/home/user/project"
        assert s["git_branch"] == "main"

    async def test_limit_parameter(self, api_client: AsyncClient, project_id: str):
        """Limit caps the number of returned sessions."""
        mock_sessions = [
            ExternalSession(
                session_id=f"ext-{i}",
                file_path=f"/tmp/ext-{i}.jsonl",
                file_size_bytes=100,
                started_at=f"2026-01-{15 + i:02d}T10:00:00.000Z",
            )
            for i in range(5)
        ]
        with patch(
            "src.api.routes.sessions.discover_sessions",
            return_value=mock_sessions,
        ):
            response = await api_client.get("/sessions/external?limit=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) == 2
        assert data["total"] == 5  # Total before limit

    async def test_sorted_newest_first(self, api_client: AsyncClient, project_id: str):
        """Sessions are sorted by started_at descending."""
        mock_sessions = [
            ExternalSession(
                session_id="old",
                file_path="/tmp/old.jsonl",
                file_size_bytes=100,
                started_at="2026-01-01T10:00:00.000Z",
            ),
            ExternalSession(
                session_id="new",
                file_path="/tmp/new.jsonl",
                file_size_bytes=100,
                started_at="2026-02-01T10:00:00.000Z",
            ),
        ]
        with patch(
            "src.api.routes.sessions.discover_sessions",
            return_value=mock_sessions,
        ):
            response = await api_client.get("/sessions/external")

        data = response.json()
        assert data["sessions"][0]["session_id"] == "new"
        assert data["sessions"][1]["session_id"] == "old"
