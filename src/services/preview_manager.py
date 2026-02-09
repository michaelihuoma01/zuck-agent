"""Preview Manager — manages dev server subprocesses for project live previews."""

import asyncio
import json
import logging
import os
import shlex
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.models.project import Project
from src.utils.project_detector import detect_project_type, PORT_FLAG_MAP

logger = logging.getLogger(__name__)

# How long to wait after Popen to verify the process survives startup
STARTUP_GRACE_SECONDS = 1.5
# Max stderr lines to capture from a crashed process
MAX_STDERR_LINES = 30


@dataclass
class ProcessInfo:
    pid: int
    port: int
    project_id: str
    project_path: str
    started_at: datetime
    process: subprocess.Popen | None


@dataclass
class PreviewStatus:
    running: bool
    url: str | None = None
    port: int | None = None
    pid: int | None = None
    uptime_seconds: int | None = None
    project_type: str | None = None
    error: str | None = None


class PreviewManager:
    """Manages dev server subprocesses for project previews."""

    PID_DIR = Path("data/previews")

    def __init__(self) -> None:
        self._processes: dict[str, ProcessInfo] = {}
        self._tailscale_ip: str | None = None
        self._tailscale_checked: bool = False
        self.PID_DIR.mkdir(parents=True, exist_ok=True)

    def _log_path(self, project_id: str) -> Path:
        return self.PID_DIR / f"{project_id}.log"

    def _read_crash_log(self, project_id: str) -> str | None:
        """Read the last N lines of a project's stderr log, then delete it."""
        log_file = self._log_path(project_id)
        if not log_file.is_file():
            return None
        try:
            text = log_file.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                return None
            lines = text.splitlines()
            tail = lines[-MAX_STDERR_LINES:]
            return "\n".join(tail)
        except OSError:
            return None

    async def start_preview(self, project: Project) -> PreviewStatus:
        if not project.dev_command or not project.dev_port:
            return PreviewStatus(running=False, error="No dev_command configured for this project")

        if project.id in self._processes:
            info = self._processes[project.id]
            if self._is_alive(info):
                return PreviewStatus(
                    running=True,
                    url=self._build_url(info.port),
                    port=info.port,
                    pid=info.pid,
                    uptime_seconds=self._uptime(info),
                    error="Preview already running for this project",
                )

        _, _, project_type = detect_project_type(project.path)

        # Find a free port — start from the preferred port, scan upward
        actual_port = self._find_free_port(project.dev_port)
        port_changed = actual_port != project.dev_port

        # Build the command, injecting a port override if needed
        cmd = project.dev_command
        env = None
        if port_changed:
            cmd, env = self._apply_port_override(cmd, actual_port, project_type)

        if project_type == "cra":
            env = {**(env or os.environ), "HOST": "0.0.0.0", "BROWSER": "none"}
            if port_changed:
                env["PORT"] = str(actual_port)

        args = shlex.split(cmd)

        # Redirect stderr to a log file so we can diagnose crashes
        log_file = self._log_path(project.id)
        try:
            stderr_fh = open(log_file, "w", encoding="utf-8")
        except OSError:
            stderr_fh = subprocess.DEVNULL

        try:
            proc = subprocess.Popen(
                args,
                cwd=project.path,
                stdout=subprocess.DEVNULL,
                stderr=stderr_fh,
                env=env,
                start_new_session=True,
            )
        except (OSError, FileNotFoundError) as e:
            if stderr_fh is not subprocess.DEVNULL:
                stderr_fh.close()
            logger.error("Failed to start preview for project %s: %s", project.id, e)
            return PreviewStatus(running=False, error=f"Failed to start dev server: {e}")

        # Close our handle — the subprocess inherited it
        if stderr_fh is not subprocess.DEVNULL:
            stderr_fh.close()

        # Grace period: wait briefly to verify the process survives startup
        await asyncio.sleep(STARTUP_GRACE_SECONDS)

        if proc.poll() is not None:
            # Process died during startup
            exit_code = proc.returncode
            crash_output = self._read_crash_log(project.id)
            error_msg = f"Dev server exited immediately (code {exit_code})"
            if crash_output:
                short = "\n".join(crash_output.splitlines()[-5:])
                error_msg += f":\n{short}"
            logger.error(
                "Preview for project %s died during startup (exit=%d): %s",
                project.id, exit_code, crash_output or "(no output)",
            )
            return PreviewStatus(running=False, port=actual_port, error=error_msg)

        now = datetime.now(timezone.utc)
        info = ProcessInfo(
            pid=proc.pid,
            port=actual_port,
            project_id=project.id,
            project_path=project.path,
            started_at=now,
            process=proc,
        )
        self._processes[project.id] = info
        self._write_pid_file(project.id, info)

        logger.info(
            "Started preview for project %s (pid=%d, port=%d, cmd=%s)",
            project.id, proc.pid, actual_port, cmd,
        )

        return PreviewStatus(
            running=True,
            url=self._build_url(actual_port),
            port=actual_port,
            pid=proc.pid,
            uptime_seconds=0,
            project_type=project_type,
        )

    async def stop_preview(self, project_id: str) -> PreviewStatus:
        info = self._processes.get(project_id)
        if not info:
            return PreviewStatus(running=False, error="No preview running for this project")

        self._kill_process(info)
        del self._processes[project_id]
        self._remove_pid_file(project_id)

        logger.info("Stopped preview for project %s (pid=%d)", project_id, info.pid)
        return PreviewStatus(running=False)

    def get_status(self, project_id: str) -> PreviewStatus:
        info = self._processes.get(project_id)
        if not info or not self._is_alive(info):
            if info:
                # Process died — try to read the crash log for a useful error
                crash_output = self._read_crash_log(project_id)
                del self._processes[project_id]
                self._remove_pid_file(project_id)
                if crash_output:
                    short = "\n".join(crash_output.splitlines()[-5:])
                    return PreviewStatus(
                        running=False,
                        error=f"Dev server crashed:\n{short}",
                    )
            return PreviewStatus(running=False)

        _, _, project_type = detect_project_type(info.project_path)

        return PreviewStatus(
            running=True,
            url=self._build_url(info.port),
            port=info.port,
            pid=info.pid,
            uptime_seconds=self._uptime(info),
            project_type=project_type,
        )

    def _find_free_port(self, preferred: int, max_attempts: int = 20) -> int:
        """Find a free port starting from ``preferred``, scanning upward."""
        for offset in range(max_attempts):
            port = preferred + offset
            if not self.detect_running(port):
                return port
        # Fallback: let the OS pick one
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    @staticmethod
    def _apply_port_override(
        cmd: str, port: int, project_type: str | None,
    ) -> tuple[str, dict[str, str] | None]:
        """Inject a port flag into the dev command for the given framework.

        Returns (modified_cmd, env_dict_or_None).
        """
        env = None

        if project_type == "django":
            # Django embeds the port in the address: 0.0.0.0:8001 → 0.0.0.0:<port>
            import re
            cmd = re.sub(r"0\.0\.0\.0:\d+", f"0.0.0.0:{port}", cmd)
        elif project_type == "cra":
            # CRA uses PORT env var — handled by caller, just pass env
            env = {**os.environ, "PORT": str(port)}
        elif project_type in PORT_FLAG_MAP:
            flag = PORT_FLAG_MAP[project_type].format(port=port)
            # npm run dev commands need -- before extra flags
            if cmd.startswith("npm ") and " -- " in cmd:
                cmd = f"{cmd} {flag}"
            elif cmd.startswith("npm "):
                cmd = f"{cmd} -- {flag}"
            else:
                cmd = f"{cmd} {flag}"
        # For "node" / unknown types, we can't inject a port — try anyway

        return (cmd, env)

    def detect_running(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            return sock.connect_ex(("127.0.0.1", port)) == 0

    async def cleanup_all(self) -> None:
        for project_id, info in list(self._processes.items()):
            self._kill_process(info)
            self._remove_pid_file(project_id)
            logger.info("Cleaned up preview for project %s (pid=%d)", project_id, info.pid)
        self._processes.clear()

    def _recover_orphans(self) -> None:
        if not self.PID_DIR.exists():
            return

        for pid_file in self.PID_DIR.glob("*.pid"):
            project_id = pid_file.stem
            try:
                data = json.loads(pid_file.read_text(encoding="utf-8"))
                pid = data["pid"]
                port = data["port"]
                project_path = data["project_path"]
                started_at_str = data["started_at"]
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning("Invalid PID file %s: %s", pid_file, e)
                pid_file.unlink(missing_ok=True)
                continue

            if not self._pid_exists(pid):
                logger.info("Orphaned PID file %s (pid %d dead), removing", pid_file, pid)
                pid_file.unlink(missing_ok=True)
                continue

            started_at = datetime.fromisoformat(started_at_str)
            info = ProcessInfo(
                pid=pid,
                port=port,
                project_id=project_id,
                project_path=project_path,
                started_at=started_at,
                process=None,
            )
            self._processes[project_id] = info
            logger.info("Recovered orphaned preview for project %s (pid=%d, port=%d)", project_id, pid, port)

    def _get_tailscale_ip(self) -> str | None:
        if self._tailscale_checked:
            return self._tailscale_ip

        self._tailscale_checked = True
        try:
            result = subprocess.run(
                ["tailscale", "ip", "-4"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                ip = result.stdout.strip().split("\n")[0].strip()
                if ip:
                    self._tailscale_ip = ip
        except (OSError, subprocess.TimeoutExpired):
            pass

        return self._tailscale_ip

    def _get_lan_ip(self) -> str | None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except OSError:
            return None

    def _build_url(self, port: int) -> str:
        ts_ip = self._get_tailscale_ip()
        if ts_ip:
            return f"http://{ts_ip}:{port}"

        lan_ip = self._get_lan_ip()
        if lan_ip:
            return f"http://{lan_ip}:{port}"

        return f"http://localhost:{port}"

    def _write_pid_file(self, project_id: str, info: ProcessInfo) -> None:
        pid_file = self.PID_DIR / f"{project_id}.pid"
        data = {
            "pid": info.pid,
            "port": info.port,
            "project_id": info.project_id,
            "project_path": info.project_path,
            "started_at": info.started_at.isoformat(),
        }
        pid_file.write_text(json.dumps(data), encoding="utf-8")

    def _remove_pid_file(self, project_id: str) -> None:
        pid_file = self.PID_DIR / f"{project_id}.pid"
        pid_file.unlink(missing_ok=True)

    def _is_alive(self, info: ProcessInfo) -> bool:
        if info.process is not None:
            return info.process.poll() is None
        return self._pid_exists(info.pid)

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    @staticmethod
    def _kill_process(info: ProcessInfo) -> None:
        try:
            if info.process is not None:
                info.process.terminate()
                try:
                    info.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    info.process.kill()
            else:
                os.kill(info.pid, signal.SIGTERM)
                for _ in range(50):
                    time.sleep(0.1)
                    try:
                        os.kill(info.pid, 0)
                    except (OSError, ProcessLookupError):
                        return
                try:
                    os.kill(info.pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
        except (OSError, ProcessLookupError):
            pass

    @staticmethod
    def _uptime(info: ProcessInfo) -> int:
        delta = datetime.now(timezone.utc) - info.started_at
        return int(delta.total_seconds())


_preview_manager: PreviewManager | None = None


def get_preview_manager() -> PreviewManager:
    global _preview_manager
    if _preview_manager is None:
        _preview_manager = PreviewManager()
    return _preview_manager


def reset_preview_manager() -> None:
    global _preview_manager
    _preview_manager = None
