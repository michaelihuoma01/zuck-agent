"""Tests for the PreviewManager service.

Tests src/services/preview_manager.py — lifecycle management of dev server
subprocesses including start/stop, PID file handling, port detection,
orphan recovery, and URL construction.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.preview_manager import (
    PreviewManager,
    PreviewStatus,
    ProcessInfo,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def pid_dir():
    """Provide a temporary directory for PID files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(os.path.realpath(tmpdir))


@pytest.fixture
def project_dir():
    """Provide a temporary directory simulating a project root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.realpath(tmpdir)


@pytest.fixture
def make_project(project_dir):
    """Factory to create a mock Project with configurable fields."""

    def _make(
        *,
        project_id: str = "proj-1",
        dev_command: str | None = "npm run dev -- --host 0.0.0.0",
        dev_port: int | None = 5173,
        path: str | None = None,
    ):
        p = MagicMock()
        p.id = project_id
        p.dev_command = dev_command
        p.dev_port = dev_port
        p.path = path or project_dir
        return p

    return _make


@pytest.fixture
def manager(pid_dir):
    """Create a PreviewManager instance with a temporary PID directory."""
    mgr = PreviewManager.__new__(PreviewManager)
    mgr._processes = {}
    mgr._tailscale_ip = None
    mgr._tailscale_checked = True
    mgr.PID_DIR = pid_dir
    return mgr


@pytest.fixture(autouse=True)
def _no_startup_delay():
    """Skip the asyncio.sleep grace period in start_preview for all tests."""
    with patch("asyncio.sleep", new_callable=AsyncMock):
        yield


# =============================================================================
# start_preview
# =============================================================================


class TestStartPreview:
    """Tests for PreviewManager.start_preview()."""

    async def test_start_preview_success(self, manager, make_project):
        """Starting a preview launches a subprocess and returns running status."""
        project = make_project()

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None  # Still running

        with patch("subprocess.Popen", return_value=mock_proc) as popen_mock, \
             _mock_port_free(), \
             _mock_detect_vite():
            status = await manager.start_preview(project)

        assert status.running is True
        assert status.pid == 12345
        assert status.port == 5173
        assert status.error is None

        # Popen should have been called with shlex-split command (list, not string)
        popen_mock.assert_called_once()
        call_args = popen_mock.call_args
        args_passed = call_args[0][0] if call_args[0] else call_args[1].get("args")
        assert isinstance(args_passed, list)

    async def test_start_preview_creates_pid_file(self, manager, make_project, pid_dir):
        """Starting a preview writes a JSON PID file to the PID directory."""
        project = make_project(project_id="proj-42")

        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        pid_file = pid_dir / "proj-42.pid"
        assert pid_file.exists()

        data = json.loads(pid_file.read_text())
        assert data["pid"] == 9999
        assert data["port"] == 5173
        assert data["project_id"] == "proj-42"
        assert "started_at" in data

    async def test_start_preview_port_occupied_reroutes(self, manager, make_project):
        """When preferred port is in use, manager finds the next free port."""
        project = make_project(dev_port=5173)

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None  # Still running

        # Port 5173 is in use, 5174 is free
        call_count = 0

        def connect_ex_side_effect(addr):
            nonlocal call_count
            call_count += 1
            _, port = addr
            return 0 if port == 5173 else 1  # 0 = in use, 1 = free

        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)
        mock_sock.connect_ex.side_effect = connect_ex_side_effect

        with patch("subprocess.Popen", return_value=mock_proc), \
             patch("socket.socket", return_value=mock_sock), \
             _mock_detect_vite():
            status = await manager.start_preview(project)

        assert status.running is True
        assert status.port == 5174  # Rerouted to next free port

    async def test_start_preview_no_dev_command(self, manager, make_project):
        """Starting without a dev_command should return an error."""
        project = make_project(dev_command=None, dev_port=None)

        status = await manager.start_preview(project)

        assert status.running is False
        assert status.error is not None

    async def test_start_preview_already_running(self, manager, make_project):
        """Starting when a preview is already running returns error/running status."""
        project = make_project()

        mock_proc = MagicMock()
        mock_proc.pid = 1111
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            first = await manager.start_preview(project)
            assert first.running is True

        # Second start should indicate already running
        with _mock_port_free():
            second = await manager.start_preview(project)

        # Manager returns running=True with an error message about already running
        assert second.running is True
        assert second.error is not None
        assert "already running" in second.error.lower()

    async def test_start_preview_uses_shlex_not_shell(self, manager, make_project):
        """Security: commands are split with shlex, not run with shell=True."""
        project = make_project(dev_command="npm run dev -- --host 0.0.0.0")

        mock_proc = MagicMock()
        mock_proc.pid = 5555
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc) as popen_mock, \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        call_kwargs = popen_mock.call_args[1] if popen_mock.call_args[1] else {}
        # shell=True should NOT be used
        assert call_kwargs.get("shell") is not True

    async def test_start_preview_no_dev_port(self, manager, make_project):
        """Starting with dev_command but no dev_port should return error."""
        project = make_project(dev_command="npm run dev", dev_port=None)

        status = await manager.start_preview(project)

        assert status.running is False
        assert status.error is not None

    async def test_start_preview_cra_sets_host_env(self, manager, make_project):
        """CRA projects set HOST=0.0.0.0 in environment instead of CLI flag."""
        project = make_project(dev_command="npm start", dev_port=3000)

        mock_proc = MagicMock()
        mock_proc.pid = 6666
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc) as popen_mock, \
             _mock_port_free(), \
             patch(
                 "src.services.preview_manager.detect_project_type",
                 return_value=("npm start", 3000, "cra"),
             ):
            await manager.start_preview(project)

        call_kwargs = popen_mock.call_args[1]
        env = call_kwargs.get("env")
        assert env is not None
        assert env.get("HOST") == "0.0.0.0"


    async def test_start_preview_process_dies_immediately(self, manager, make_project):
        """If the process exits during startup grace period, return error with stderr."""
        project = make_project()

        mock_proc = MagicMock()
        mock_proc.pid = 7777
        mock_proc.poll.return_value = 1  # Already exited
        mock_proc.returncode = 1

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            # Write fake stderr to the log file
            log_file = manager.PID_DIR / f"{project.id}.log"
            log_file.write_text("Error: Cannot find module 'next'\n")

            status = await manager.start_preview(project)

        assert status.running is False
        assert status.error is not None
        assert "exited immediately" in status.error.lower() or "Cannot find" in status.error

    async def test_start_preview_crash_no_pid_file(self, manager, make_project, pid_dir):
        """If process dies during startup, no PID file should be written."""
        project = make_project(project_id="crash-proj")

        mock_proc = MagicMock()
        mock_proc.pid = 8888
        mock_proc.poll.return_value = 1
        mock_proc.returncode = 1

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        pid_file = pid_dir / "crash-proj.pid"
        assert not pid_file.exists()
        assert "crash-proj" not in manager._processes


# =============================================================================
# stop_preview
# =============================================================================


class TestStopPreview:
    """Tests for PreviewManager.stop_preview()."""

    async def test_stop_preview_success(self, manager, make_project, pid_dir):
        """Stopping a running preview terminates the process and cleans up."""
        project = make_project(project_id="proj-stop")

        mock_proc = MagicMock()
        mock_proc.pid = 7777
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        status = await manager.stop_preview("proj-stop")

        assert status.running is False
        mock_proc.terminate.assert_called()

    async def test_stop_preview_removes_pid_file(self, manager, make_project, pid_dir):
        """Stopping removes the PID file."""
        project = make_project(project_id="proj-pid")

        mock_proc = MagicMock()
        mock_proc.pid = 8888
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        pid_file = pid_dir / "proj-pid.pid"
        assert pid_file.exists()

        await manager.stop_preview("proj-pid")

        assert not pid_file.exists()

    async def test_stop_preview_not_running(self, manager):
        """Stopping when nothing is running returns error about not running."""
        status = await manager.stop_preview("nonexistent-project")

        assert status.running is False
        assert status.error is not None

    async def test_stop_preview_removes_from_processes(self, manager, make_project):
        """After stop, the project is no longer tracked in _processes."""
        project = make_project(project_id="proj-track")

        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        assert "proj-track" in manager._processes

        await manager.stop_preview("proj-track")

        assert "proj-track" not in manager._processes


# =============================================================================
# get_status
# =============================================================================


class TestGetStatus:
    """Tests for PreviewManager.get_status()."""

    async def test_get_status_running(self, manager, make_project):
        """Status of a running preview includes pid, port, url."""
        project = make_project(project_id="proj-status")

        mock_proc = MagicMock()
        mock_proc.pid = 3333
        mock_proc.poll.return_value = None  # Still running

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        with _mock_detect_vite():
            status = manager.get_status("proj-status")

        assert status.running is True
        assert status.pid == 3333
        assert status.port == 5173

    async def test_get_status_not_running(self, manager):
        """Status when no preview is tracked returns running=False."""
        status = manager.get_status("no-such-project")

        assert status.running is False
        assert status.pid is None
        assert status.port is None
        assert status.url is None

    async def test_get_status_includes_url(self, manager, make_project):
        """Status of a running preview includes a URL with the port."""
        project = make_project(project_id="proj-url")

        mock_proc = MagicMock()
        mock_proc.pid = 4444
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        with _mock_detect_vite():
            status = manager.get_status("proj-url")

        assert status.url is not None
        assert "5173" in status.url

    async def test_get_status_uptime(self, manager, make_project):
        """Status includes uptime_seconds for running previews."""
        project = make_project(project_id="proj-uptime")

        mock_proc = MagicMock()
        mock_proc.pid = 5555
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        with _mock_detect_vite():
            status = manager.get_status("proj-uptime")

        assert status.uptime_seconds is not None
        assert status.uptime_seconds >= 0

    async def test_get_status_cleans_dead_process(self, manager, make_project, pid_dir):
        """If the tracked process is dead, get_status cleans it up."""
        project = make_project(project_id="proj-dead")

        mock_proc = MagicMock()
        mock_proc.pid = 6666
        mock_proc.poll.return_value = None  # Alive during start

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        # Now the process dies
        mock_proc.poll.return_value = 1  # Exited

        status = manager.get_status("proj-dead")

        assert status.running is False
        assert "proj-dead" not in manager._processes


# =============================================================================
# detect_running
# =============================================================================


class TestDetectRunning:
    """Tests for PreviewManager.detect_running()."""

    async def test_detect_running_port_open(self, manager):
        """Port open (connect_ex returns 0) means something is running."""
        with _mock_port_in_use():
            assert manager.detect_running(5173) is True

    async def test_detect_running_port_closed(self, manager):
        """Port closed (connect_ex returns non-zero) means nothing running."""
        with _mock_port_free():
            assert manager.detect_running(5173) is False


# =============================================================================
# cleanup_all
# =============================================================================


class TestCleanupAll:
    """Tests for PreviewManager.cleanup_all()."""

    async def test_cleanup_all_terminates_processes(self, manager, make_project):
        """cleanup_all terminates all tracked processes."""
        procs = []
        for i in range(3):
            project = make_project(
                project_id=f"proj-{i}",
                dev_port=5173 + i,
            )

            mock_proc = MagicMock()
            mock_proc.pid = 10000 + i
            mock_proc.poll.return_value = None
            procs.append(mock_proc)

            with patch("subprocess.Popen", return_value=mock_proc), \
                 _mock_port_free(), \
                 _mock_detect_vite():
                await manager.start_preview(project)

        await manager.cleanup_all()

        for proc in procs:
            proc.terminate.assert_called()

    async def test_cleanup_all_clears_processes_dict(self, manager, make_project):
        """cleanup_all empties the _processes tracking dict."""
        project = make_project(project_id="proj-clear")

        mock_proc = MagicMock()
        mock_proc.pid = 9876
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        assert len(manager._processes) == 1

        await manager.cleanup_all()

        assert len(manager._processes) == 0

    async def test_cleanup_all_removes_pid_files(self, manager, make_project, pid_dir):
        """cleanup_all removes all PID files."""
        project = make_project(project_id="proj-files")

        mock_proc = MagicMock()
        mock_proc.pid = 5432
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        assert (pid_dir / "proj-files.pid").exists()

        await manager.cleanup_all()

        assert not (pid_dir / "proj-files.pid").exists()

    async def test_cleanup_all_empty(self, manager):
        """cleanup_all with no processes is a no-op (no error)."""
        await manager.cleanup_all()  # Should not raise


# =============================================================================
# PID file lifecycle
# =============================================================================


class TestPidFileLifecycle:
    """Tests for PID file creation and removal."""

    async def test_pid_file_is_valid_json(self, manager, make_project, pid_dir):
        """PID file is valid JSON with expected fields."""
        project = make_project(project_id="pid-json", dev_port=3000)

        mock_proc = MagicMock()
        mock_proc.pid = 6666
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        pid_file = pid_dir / "pid-json.pid"
        data = json.loads(pid_file.read_text())

        assert data["pid"] == 6666
        assert data["port"] == 3000
        assert data["project_id"] == "pid-json"
        assert "project_path" in data
        assert "started_at" in data

    async def test_pid_file_removed_on_stop(self, manager, make_project, pid_dir):
        """PID file is removed when preview stops."""
        project = make_project(project_id="pid-rm")

        mock_proc = MagicMock()
        mock_proc.pid = 7777
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc), \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        assert (pid_dir / "pid-rm.pid").exists()

        await manager.stop_preview("pid-rm")

        assert not (pid_dir / "pid-rm.pid").exists()


# =============================================================================
# Orphan recovery
# =============================================================================


class TestOrphanRecovery:
    """Tests for _recover_orphans() — restart tracking from PID files."""

    async def test_recover_living_orphan(self, manager, pid_dir):
        """PID file with a live process is re-tracked in _processes."""
        pid_file = pid_dir / "orphan-alive.pid"
        pid_data = {
            "pid": 54321,
            "port": 5173,
            "project_id": "orphan-alive",
            "project_path": "/tmp/fake-project",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        pid_file.write_text(json.dumps(pid_data))

        with patch.object(PreviewManager, "_pid_exists", return_value=True):
            manager._recover_orphans()

        assert "orphan-alive" in manager._processes
        info = manager._processes["orphan-alive"]
        assert info.pid == 54321
        assert info.port == 5173
        assert info.process is None  # Recovered, no Popen handle

    async def test_recover_stale_orphan(self, manager, pid_dir):
        """PID file with a dead process is removed, not tracked."""
        pid_file = pid_dir / "orphan-dead.pid"
        pid_data = {
            "pid": 99999,
            "port": 3000,
            "project_id": "orphan-dead",
            "project_path": "/tmp/dead-project",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        pid_file.write_text(json.dumps(pid_data))

        with patch.object(PreviewManager, "_pid_exists", return_value=False):
            manager._recover_orphans()

        assert not pid_file.exists()
        assert "orphan-dead" not in manager._processes

    async def test_recover_malformed_pid_file(self, manager, pid_dir):
        """PID file with non-JSON content is removed."""
        pid_file = pid_dir / "orphan-bad.pid"
        pid_file.write_text("not-json-at-all")

        manager._recover_orphans()

        assert not pid_file.exists()
        assert "orphan-bad" not in manager._processes

    async def test_recover_pid_file_missing_keys(self, manager, pid_dir):
        """PID file with missing required keys is removed."""
        pid_file = pid_dir / "orphan-partial.pid"
        pid_file.write_text(json.dumps({"pid": 12345}))  # Missing port, etc.

        manager._recover_orphans()

        assert not pid_file.exists()
        assert "orphan-partial" not in manager._processes

    async def test_recover_multiple_orphans(self, manager, pid_dir):
        """Multiple PID files are all processed."""
        now = datetime.now(timezone.utc).isoformat()

        for i in range(3):
            pid_file = pid_dir / f"multi-{i}.pid"
            pid_data = {
                "pid": 20000 + i,
                "port": 5000 + i,
                "project_id": f"multi-{i}",
                "project_path": f"/tmp/project-{i}",
                "started_at": now,
            }
            pid_file.write_text(json.dumps(pid_data))

        with patch.object(PreviewManager, "_pid_exists", return_value=True):
            manager._recover_orphans()

        assert len(manager._processes) == 3
        for i in range(3):
            assert f"multi-{i}" in manager._processes

    async def test_recover_no_pid_dir(self, manager):
        """_recover_orphans is a no-op if PID dir doesn't exist."""
        manager.PID_DIR = Path("/nonexistent/path/that/does/not/exist")
        manager._recover_orphans()  # Should not raise


# =============================================================================
# URL construction
# =============================================================================


class TestUrlConstruction:
    """Tests for _build_url(), _get_tailscale_ip(), _get_lan_ip()."""

    async def test_url_uses_tailscale_ip_when_available(self, manager):
        """When Tailscale IP is available, URL uses it."""
        with patch.object(manager, "_get_tailscale_ip", return_value="100.64.1.1"), \
             patch.object(manager, "_get_lan_ip", return_value="192.168.1.100"):
            url = manager._build_url(5173)

        assert "100.64.1.1" in url
        assert ":5173" in url

    async def test_url_falls_back_to_lan_ip(self, manager):
        """When no Tailscale, URL uses LAN IP."""
        with patch.object(manager, "_get_tailscale_ip", return_value=None), \
             patch.object(manager, "_get_lan_ip", return_value="192.168.1.50"):
            url = manager._build_url(3000)

        assert "192.168.1.50" in url
        assert ":3000" in url

    async def test_url_falls_back_to_localhost(self, manager):
        """When no Tailscale and no LAN IP, URL uses localhost."""
        with patch.object(manager, "_get_tailscale_ip", return_value=None), \
             patch.object(manager, "_get_lan_ip", return_value=None):
            url = manager._build_url(8080)

        assert "localhost" in url or "127.0.0.1" in url
        assert ":8080" in url

    async def test_url_uses_http_scheme(self, manager):
        """URL uses http:// (not https://) since dev servers are plain HTTP."""
        with patch.object(manager, "_get_tailscale_ip", return_value=None), \
             patch.object(manager, "_get_lan_ip", return_value=None):
            url = manager._build_url(5173)

        assert url.startswith("http://")

    async def test_get_tailscale_ip_when_available(self, manager):
        """_get_tailscale_ip returns IP from tailscale command output."""
        # Reset cache so the method actually runs
        manager._tailscale_checked = False
        manager._tailscale_ip = None

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "100.100.1.1\n"

        with patch("subprocess.run", return_value=mock_result):
            ip = manager._get_tailscale_ip()

        assert ip == "100.100.1.1"

    async def test_get_tailscale_ip_not_installed(self, manager):
        """_get_tailscale_ip returns None when tailscale is not available."""
        manager._tailscale_checked = False
        manager._tailscale_ip = None

        with patch("subprocess.run", side_effect=FileNotFoundError):
            ip = manager._get_tailscale_ip()

        assert ip is None

    async def test_get_tailscale_ip_not_connected(self, manager):
        """_get_tailscale_ip returns None when tailscale returns non-zero."""
        manager._tailscale_checked = False
        manager._tailscale_ip = None

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            ip = manager._get_tailscale_ip()

        assert ip is None

    async def test_get_tailscale_ip_cached(self, manager):
        """_get_tailscale_ip caches the result after first call."""
        manager._tailscale_checked = True
        manager._tailscale_ip = "100.50.50.50"

        # Should not call subprocess.run since it's cached
        with patch("subprocess.run") as mock_run:
            ip = manager._get_tailscale_ip()

        mock_run.assert_not_called()
        assert ip == "100.50.50.50"


# =============================================================================
# Process subprocess.Popen working directory
# =============================================================================


class TestSubprocessConfiguration:
    """Tests verifying that Popen is invoked with correct cwd, env, etc."""

    async def test_popen_cwd_is_project_path(self, manager, make_project, project_dir):
        """Subprocess is started in the project's directory."""
        project = make_project()

        mock_proc = MagicMock()
        mock_proc.pid = 2222
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc) as popen_mock, \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        call_kwargs = popen_mock.call_args[1]
        assert os.path.realpath(call_kwargs["cwd"]) == project_dir

    async def test_popen_stdout_devnull_stderr_logged(self, manager, make_project):
        """Subprocess stdout goes to DEVNULL, stderr goes to a log file."""
        project = make_project()

        mock_proc = MagicMock()
        mock_proc.pid = 3333
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc) as popen_mock, \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        call_kwargs = popen_mock.call_args[1]
        import subprocess as sp
        assert call_kwargs.get("stdout") == sp.DEVNULL
        # stderr is redirected to a log file (not DEVNULL)
        assert call_kwargs.get("stderr") != sp.DEVNULL

    async def test_popen_start_new_session(self, manager, make_project):
        """Subprocess is started in a new session (detached from ZURK)."""
        project = make_project()

        mock_proc = MagicMock()
        mock_proc.pid = 4444
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc) as popen_mock, \
             _mock_port_free(), \
             _mock_detect_vite():
            await manager.start_preview(project)

        call_kwargs = popen_mock.call_args[1]
        assert call_kwargs.get("start_new_session") is True


# =============================================================================
# _is_alive and _pid_exists
# =============================================================================


class TestIsAlive:
    """Tests for _is_alive and _pid_exists helpers."""

    async def test_is_alive_with_popen_running(self, manager):
        """Process with Popen handle that is still running."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        info = ProcessInfo(
            pid=1, port=1, project_id="x", project_path="/x",
            started_at=datetime.now(timezone.utc), process=mock_proc,
        )
        assert manager._is_alive(info) is True

    async def test_is_alive_with_popen_exited(self, manager):
        """Process with Popen handle that has exited."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        info = ProcessInfo(
            pid=1, port=1, project_id="x", project_path="/x",
            started_at=datetime.now(timezone.utc), process=mock_proc,
        )
        assert manager._is_alive(info) is False

    async def test_is_alive_recovered_process_alive(self, manager):
        """Recovered process (no Popen handle) that is alive."""
        info = ProcessInfo(
            pid=1, port=1, project_id="x", project_path="/x",
            started_at=datetime.now(timezone.utc), process=None,
        )
        with patch.object(PreviewManager, "_pid_exists", return_value=True):
            assert manager._is_alive(info) is True

    async def test_is_alive_recovered_process_dead(self, manager):
        """Recovered process (no Popen handle) that is dead."""
        info = ProcessInfo(
            pid=1, port=1, project_id="x", project_path="/x",
            started_at=datetime.now(timezone.utc), process=None,
        )
        with patch.object(PreviewManager, "_pid_exists", return_value=False):
            assert manager._is_alive(info) is False


# =============================================================================
# Helpers
# =============================================================================


def _mock_port_free():
    """Context manager: mock socket.connect_ex to return non-zero (port free)."""
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)
    mock_sock.connect_ex.return_value = 1  # Port free

    return patch("socket.socket", return_value=mock_sock)


def _mock_port_in_use():
    """Context manager: mock socket.connect_ex to return 0 (port in use)."""
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)
    mock_sock.connect_ex.return_value = 0  # Port in use

    return patch("socket.socket", return_value=mock_sock)


def _mock_detect_vite():
    """Context manager: mock detect_project_type to return vite."""
    return patch(
        "src.services.preview_manager.detect_project_type",
        return_value=("npm run dev -- --host 0.0.0.0", 5173, "vite"),
    )
