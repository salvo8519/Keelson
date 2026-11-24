"""End-to-end test: render the default project and run its own checks and test suites."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import Render

pytestmark = pytest.mark.generated


def _run(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    output = result.stdout[-4000:] + result.stderr[-2000:]
    assert result.returncode == 0, f"{' '.join(command)} failed in {cwd}:\n{output}"
    return result.stdout


def test_default_project_backend_passes_its_checks(render: Render) -> None:
    """Lint, message catalogs and the backend test suite (PostgreSQL tests included)."""
    backend = render({"project_name": "acme_service"}) / "backend"
    _run(["uv", "sync", "--quiet"], backend)
    _run(["uv", "run", "ruff", "check", "app", "tests", "cli"], backend)
    _run(["uv", "run", "ruff", "format", "--check", "app", "tests", "cli"], backend)
    _run(["uv", "run", "python", "-m", "app.core.i18n_catalog", "check"], backend)
    summary = _run(["uv", "run", "pytest", "-q", "-rs", "-p", "no:cacheprovider"], backend)
    # The PostgreSQL tests (row level security, API keys, migrations) skip themselves without a
    # database; here a skip means the check did not run.
    assert "skipped" not in summary.splitlines()[-1], summary[-3000:]


def test_default_project_frontend_passes_its_checks(render: Render) -> None:
    """The official React frontend: Biome, translations, tsc and Vite against the Keelson API."""
    frontend = render({"project_name": "acme_service"}) / "frontend"
    _run(["bun", "install"], frontend)
    _run(["bunx", "biome", "check", "./"], frontend)
    _run(["bun", "run", "i18n:check"], frontend)
    _run(["bun", "run", "build"], frontend)
