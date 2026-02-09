"""Project type detection for live preview dev server commands."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# How each framework accepts a port override via CLI args.
# {project_type: port_flag_template}  — "{port}" is replaced with the actual port.
# CRA uses an env var instead (handled separately in PreviewManager).
PORT_FLAG_MAP: dict[str, str] = {
    "vite": "--port {port}",
    "nextjs": "-p {port}",
    "nuxt": "--port {port}",
    "flask": "-p {port}",
    # Django: port is part of the address arg, handled separately
    # CRA: uses PORT env var, handled separately
}


def _has_host_binding(script: str) -> bool:
    """Check if a dev script already binds to a host (0.0.0.0 or --host)."""
    return "--host" in script or "-H " in script or "0.0.0.0" in script


def detect_project_type(project_path: str) -> tuple[str | None, int | None, str | None]:
    """Detect the project type and appropriate dev server command.

    Reads package.json (if present) to determine the framework, then
    falls back to Python project markers. All commands bind to 0.0.0.0
    for network accessibility (unless the dev script already does so).

    Returns:
        (dev_command, dev_port, project_type) or (None, None, None)
    """
    root = Path(project_path)
    package_json = root / "package.json"

    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to parse package.json at %s", project_path)
            return (None, None, None)

        scripts = data.get("scripts", {})
        dev_script = scripts.get("dev", "")
        all_deps = {
            **data.get("dependencies", {}),
            **data.get("devDependencies", {}),
        }

        if "vite" in dev_script or "vite" in all_deps:
            host_flag = "" if _has_host_binding(dev_script) else " -- --host 0.0.0.0"
            return (f"npm run dev{host_flag}", 5173, "vite")

        if "next" in all_deps:
            host_flag = "" if _has_host_binding(dev_script) else " -- -H 0.0.0.0"
            return (f"npm run dev{host_flag}", 3000, "nextjs")

        if "react-scripts" in all_deps:
            return ("npm start", 3000, "cra")

        if "nuxt" in all_deps:
            host_flag = "" if _has_host_binding(dev_script) else " -- --host 0.0.0.0"
            return (f"npm run dev{host_flag}", 3000, "nuxt")

        if dev_script:
            return ("npm run dev", 3000, "node")

    if (root / "app.py").is_file() or (root / "wsgi.py").is_file():
        return ("flask run --host 0.0.0.0", 5000, "flask")

    if (root / "manage.py").is_file():
        return ("python manage.py runserver 0.0.0.0:8001", 8001, "django")

    return (None, None, None)
