"""End-to-end test: render the default project and run its own backend test suite."""

from __future__ import annotations

import subprocess

import pytest
from conftest import Render

pytestmark = pytest.mark.generated


def test_default_project_backend_suite_passes(render: Render) -> None:
    backend = render({"project_name": "acme_service"}) / "backend"
    subprocess.run(["uv", "sync", "--quiet"], cwd=backend, check=True)
    result = subprocess.run(
        ["uv", "run", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=backend,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
