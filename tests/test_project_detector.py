"""Tests for project type detection logic.

Tests src/utils/project_detector.py — the detect_project_type() function.
Each test creates real files in a temporary directory to simulate project structures.
"""

import json
import os
import tempfile

from src.utils.project_detector import detect_project_type


class TestProjectDetector:
    """Unit tests for detect_project_type()."""

    # -----------------------------------------------------------------
    # Vite
    # -----------------------------------------------------------------

    async def test_detect_vite_project_via_dev_script(self):
        """Vite detected when scripts.dev contains 'vite'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = {
                "name": "my-vite-app",
                "scripts": {"dev": "vite"},
                "dependencies": {},
            }
            _write_json(tmpdir, "package.json", pkg)

            cmd, port, ptype = detect_project_type(tmpdir)

            assert cmd == "npm run dev -- --host 0.0.0.0"
            assert port == 5173
            assert ptype == "vite"

    async def test_detect_vite_project_via_dev_dependency(self):
        """Vite detected when 'vite' is in devDependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = {
                "name": "my-app",
                "scripts": {"dev": "vite --mode staging"},
                "devDependencies": {"vite": "^5.0.0"},
            }
            _write_json(tmpdir, "package.json", pkg)

            cmd, port, ptype = detect_project_type(tmpdir)

            assert cmd == "npm run dev -- --host 0.0.0.0"
            assert port == 5173
            assert ptype == "vite"

    # -----------------------------------------------------------------
    # Next.js
    # -----------------------------------------------------------------

    async def test_detect_nextjs_project(self):
        """Next.js detected when 'next' is in dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = {
                "name": "my-next-app",
                "scripts": {"dev": "next dev"},
                "dependencies": {"next": "14.1.0", "react": "^18"},
            }
            _write_json(tmpdir, "package.json", pkg)

            cmd, port, ptype = detect_project_type(tmpdir)

            assert cmd == "npm run dev -- -H 0.0.0.0"
            assert port == 3000
            assert ptype == "nextjs"

    # -----------------------------------------------------------------
    # CRA (Create React App)
    # -----------------------------------------------------------------

    async def test_detect_cra_project(self):
        """CRA detected when 'react-scripts' is in dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = {
                "name": "my-cra-app",
                "scripts": {"start": "react-scripts start"},
                "dependencies": {"react-scripts": "5.0.1", "react": "^18"},
            }
            _write_json(tmpdir, "package.json", pkg)

            cmd, port, ptype = detect_project_type(tmpdir)

            assert cmd == "npm start"
            assert port == 3000
            assert ptype == "cra"

    # -----------------------------------------------------------------
    # Nuxt
    # -----------------------------------------------------------------

    async def test_detect_nuxt_project(self):
        """Nuxt detected when 'nuxt' is in dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = {
                "name": "my-nuxt-app",
                "scripts": {"dev": "nuxi dev"},
                "dependencies": {"nuxt": "^3.10"},
            }
            _write_json(tmpdir, "package.json", pkg)

            cmd, port, ptype = detect_project_type(tmpdir)

            assert port == 3000
            assert ptype == "nuxt"
            assert "--host 0.0.0.0" in cmd

    # -----------------------------------------------------------------
    # Generic npm project with dev script
    # -----------------------------------------------------------------

    async def test_detect_generic_npm_project(self):
        """Generic node project with a dev script but no known framework."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = {
                "name": "custom-server",
                "scripts": {"dev": "node server.js"},
                "dependencies": {"express": "^4"},
            }
            _write_json(tmpdir, "package.json", pkg)

            cmd, port, ptype = detect_project_type(tmpdir)

            assert cmd == "npm run dev"
            assert port == 3000
            assert ptype == "node"

    # -----------------------------------------------------------------
    # Flask
    # -----------------------------------------------------------------

    async def test_detect_flask_project_via_app_py(self):
        """Flask detected when app.py exists (no package.json)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _touch(tmpdir, "app.py")

            cmd, port, ptype = detect_project_type(tmpdir)

            assert cmd == "flask run --host 0.0.0.0"
            assert port == 5000
            assert ptype == "flask"

    async def test_detect_flask_project_via_wsgi_py(self):
        """Flask detected when wsgi.py exists (no package.json)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _touch(tmpdir, "wsgi.py")

            cmd, port, ptype = detect_project_type(tmpdir)

            assert cmd == "flask run --host 0.0.0.0"
            assert port == 5000
            assert ptype == "flask"

    # -----------------------------------------------------------------
    # Django
    # -----------------------------------------------------------------

    async def test_detect_django_project(self):
        """Django detected when manage.py exists (no package.json)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _touch(tmpdir, "manage.py")

            cmd, port, ptype = detect_project_type(tmpdir)

            assert cmd == "python manage.py runserver 0.0.0.0:8001"
            assert port == 8001
            assert ptype == "django"

    async def test_django_avoids_zurk_port(self):
        """Django uses port 8001 (not 8000) to avoid ZURK backend conflict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _touch(tmpdir, "manage.py")

            _, port, _ = detect_project_type(tmpdir)

            assert port == 8001

    # -----------------------------------------------------------------
    # No detectable project
    # -----------------------------------------------------------------

    async def test_no_detectable_project_type(self):
        """Empty directory returns (None, None, None)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd, port, ptype = detect_project_type(tmpdir)

            assert cmd is None
            assert port is None
            assert ptype is None

    async def test_directory_with_unrelated_files(self):
        """Directory with random files returns (None, None, None)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _touch(tmpdir, "README.md")
            _touch(tmpdir, "data.csv")
            _touch(tmpdir, "requirements.txt")

            cmd, port, ptype = detect_project_type(tmpdir)

            assert cmd is None
            assert port is None
            assert ptype is None

    # -----------------------------------------------------------------
    # Priority / precedence
    # -----------------------------------------------------------------

    async def test_vite_takes_priority_over_django(self):
        """When both package.json (Vite) AND manage.py exist, Vite wins."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = {
                "name": "fullstack-app",
                "scripts": {"dev": "vite"},
                "devDependencies": {"vite": "^5.0.0"},
            }
            _write_json(tmpdir, "package.json", pkg)
            _touch(tmpdir, "manage.py")

            cmd, port, ptype = detect_project_type(tmpdir)

            assert ptype == "vite"
            assert port == 5173

    async def test_nextjs_takes_priority_over_flask(self):
        """When both package.json (Next.js) AND app.py exist, Next.js wins."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = {
                "name": "fullstack",
                "scripts": {"dev": "next dev"},
                "dependencies": {"next": "14.0.0"},
            }
            _write_json(tmpdir, "package.json", pkg)
            _touch(tmpdir, "app.py")

            cmd, port, ptype = detect_project_type(tmpdir)

            assert ptype == "nextjs"
            assert port == 3000

    async def test_vite_detected_over_nextjs_when_both_present(self):
        """When deps have both vite and next, vite (higher priority) wins."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = {
                "name": "confused-app",
                "scripts": {"dev": "vite"},
                "dependencies": {"next": "14.0.0"},
                "devDependencies": {"vite": "^5.0.0"},
            }
            _write_json(tmpdir, "package.json", pkg)

            _, port, ptype = detect_project_type(tmpdir)

            assert ptype == "vite"
            assert port == 5173

    # -----------------------------------------------------------------
    # Edge cases
    # -----------------------------------------------------------------

    async def test_package_json_no_scripts(self):
        """package.json without scripts section does not match node frameworks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = {"name": "lib-only", "dependencies": {"lodash": "^4"}}
            _write_json(tmpdir, "package.json", pkg)

            cmd, port, ptype = detect_project_type(tmpdir)

            assert cmd is None
            assert port is None
            assert ptype is None

    async def test_package_json_empty_dev_script(self):
        """package.json with empty dev script does not match generic node."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = {
                "name": "no-dev",
                "scripts": {"test": "jest"},
                "dependencies": {"jest": "^29"},
            }
            _write_json(tmpdir, "package.json", pkg)

            cmd, port, ptype = detect_project_type(tmpdir)

            assert cmd is None
            assert port is None
            assert ptype is None

    async def test_malformed_package_json(self):
        """Malformed package.json returns (None, None, None)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "package.json")
            with open(path, "w") as f:
                f.write("{not valid json")

            cmd, port, ptype = detect_project_type(tmpdir)

            assert cmd is None
            assert port is None
            assert ptype is None

    async def test_all_commands_bind_to_0_0_0_0(self):
        """All detected commands must bind to 0.0.0.0 for network access."""
        test_cases = [
            # (package_json_content, marker_file, expected_type)
            ({"scripts": {"dev": "vite"}, "devDependencies": {"vite": "5"}}, None, "vite"),
            ({"scripts": {"dev": "next dev"}, "dependencies": {"next": "14"}}, None, "nextjs"),
            ({"scripts": {"dev": "nuxi dev"}, "dependencies": {"nuxt": "3"}}, None, "nuxt"),
            (None, "app.py", "flask"),
            (None, "manage.py", "django"),
        ]

        for pkg_content, marker_file, expected_type in test_cases:
            with tempfile.TemporaryDirectory() as tmpdir:
                if pkg_content:
                    _write_json(tmpdir, "package.json", pkg_content)
                if marker_file:
                    _touch(tmpdir, marker_file)

                cmd, _, ptype = detect_project_type(tmpdir)

                assert ptype == expected_type, f"Failed for type {expected_type}"
                assert cmd is not None, f"No command for {expected_type}"
                # CRA is special: uses HOST env var, not --host flag.
                # All others should have 0.0.0.0 in the command itself.
                if ptype != "cra":
                    assert "0.0.0.0" in cmd, (
                        f"{expected_type} command missing 0.0.0.0: {cmd}"
                    )

    async def test_vite_script_already_has_host(self):
        """If dev script already has --host, don't append it again."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = {
                "name": "my-vite-app",
                "scripts": {"dev": "vite --host 0.0.0.0"},
                "devDependencies": {"vite": "^5.0.0"},
            }
            _write_json(tmpdir, "package.json", pkg)

            cmd, port, ptype = detect_project_type(tmpdir)

            assert ptype == "vite"
            assert cmd == "npm run dev"
            assert cmd.count("--host") == 0  # Not doubled

    async def test_nextjs_script_already_has_host(self):
        """If dev script already has -H 0.0.0.0, don't append it again."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = {
                "name": "my-next-app",
                "scripts": {"dev": "next dev -H 0.0.0.0 --turbopack"},
                "dependencies": {"next": "15.0.0"},
            }
            _write_json(tmpdir, "package.json", pkg)

            cmd, port, ptype = detect_project_type(tmpdir)

            assert ptype == "nextjs"
            assert cmd == "npm run dev"
            assert "-H" not in cmd  # Not doubled

    async def test_nonexistent_path(self):
        """Nonexistent path returns (None, None, None) rather than crashing."""
        cmd, port, ptype = detect_project_type("/tmp/definitely-not-a-real-path-xyz")

        assert cmd is None
        assert port is None
        assert ptype is None


# =============================================================================
# Helpers
# =============================================================================


def _write_json(directory: str, filename: str, data: dict) -> None:
    """Write a JSON file into a directory."""
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _touch(directory: str, filename: str) -> None:
    """Create an empty file in a directory."""
    path = os.path.join(directory, filename)
    with open(path, "w") as f:
        pass
