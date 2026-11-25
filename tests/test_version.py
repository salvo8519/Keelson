"""One version per generated project: VERSION, copied into the manifests (Keelstone)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import Render


def _script(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/version.py", *args],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )


def _manifest_versions(project: Path) -> tuple[str, str, str]:
    backend = (project / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]*)"$', backend, re.MULTILINE)
    assert match, "the backend manifest has a version line"
    frontend = json.loads((project / "frontend" / "package.json").read_text(encoding="utf-8"))
    version = (project / "VERSION").read_text(encoding="utf-8").strip()
    return version, match.group(1), frontend["version"]


@pytest.fixture
def project(render: Render, tmp_path: Path) -> Path:
    """A copy of the default render, so that the cached render stays untouched."""
    copy = tmp_path / "project"
    source = render({"project_name": "acme_service"})
    shutil.copytree(source, copy, ignore=shutil.ignore_patterns("node_modules", ".venv"))
    return copy


def test_a_new_project_carries_one_version_everywhere(project: Path) -> None:
    assert _manifest_versions(project) == ("0.1.0", "0.1.0", "0.1.0")
    assert _script(project, "check").returncode == 0


@pytest.mark.parametrize(
    ("part", "expected"), [("patch", "0.1.1"), ("minor", "0.2.0"), ("major", "1.0.0")]
)
def test_a_bump_changes_every_copy(project: Path, part: str, expected: str) -> None:
    result = _script(project, "bump", part)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected
    assert _manifest_versions(project) == (expected, expected, expected)


def test_a_copy_out_of_step_fails_the_check(project: Path) -> None:
    package = project / "frontend" / "package.json"
    data = json.loads(package.read_text(encoding="utf-8"))
    data["version"] = "9.9.9"
    package.write_text(json.dumps(data), encoding="utf-8")
    result = _script(project, "check")
    assert result.returncode == 1
    assert "frontend/package.json" in result.stderr


@pytest.mark.parametrize("value", ["1.2", "v1.2.3", "01.2.3", "1.2.3-rc1", ""])
def test_only_plain_semantic_versions_are_accepted(project: Path, value: str) -> None:
    assert _script(project, "set", value).returncode != 0
    assert _manifest_versions(project) == ("0.1.0", "0.1.0", "0.1.0")


def test_the_makefile_offers_the_version_commands(project: Path) -> None:
    makefile = (project / "Makefile").read_text(encoding="utf-8")
    assert "bump-version:" in makefile and "version:" in makefile
    assert "python3 scripts/version.py check" in makefile, "make lint keeps the copies in step"
