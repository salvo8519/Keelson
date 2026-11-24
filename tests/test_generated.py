"""End-to-end test: render the default project and run its own checks and test suites."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
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


def test_default_project_documentation_builds(render: Render) -> None:
    """Zensical site of the generated project: reference from the code, strict build."""
    project = render({"project_name": "acme_service"})
    _run(["uv", "sync", "--quiet"], project / "backend")
    _run(["make", "openapi"], project)
    _run(["make", "docs-check"], project)
    _run(["make", "docs"], project)
    assert (project / "site" / "openapi.json").read_bytes() == (
        project / "openapi" / "openapi.json"
    ).read_bytes(), "the site publishes the contract"
    for lang in ("en", "it"):
        site = project / "site" / ("" if lang == "en" else lang)
        api = (site / "reference" / "api" / "index.html").read_text(encoding="utf-8")
        assert "/api/v1/api-keys" in api
        settings = (site / "reference" / "settings" / "index.html").read_text(encoding="utf-8")
        assert "SECRET_KEY" in settings


def test_default_project_api_contract(render: Render) -> None:
    """openapi/openapi.json: the same on every export, and the committed client matches it."""
    project = render({"project_name": "acme_service"})
    backend, frontend = project / "backend", project / "frontend"
    _run(["uv", "sync", "--quiet"], backend)
    _run(["make", "openapi"], project)
    _run(["make", "openapi-check"], project)
    client = frontend / "src" / "client"
    committed = {path.name: path.read_bytes() for path in sorted(client.glob("*.ts"))}
    _run(["bun", "install"], frontend)
    _run(["bun", "run", "generate-client"], frontend)
    _run(["bun", "run", "lint"], frontend)
    regenerated = {path.name: path.read_bytes() for path in sorted(client.glob("*.ts"))}
    stale = sorted(
        name
        for name in committed.keys() | regenerated.keys()
        if committed.get(name) != regenerated.get(name)
    )
    assert stale == [], f"the template's frontend client is out of date: {stale}"


def test_default_project_compose_stacks_are_valid(render: Render) -> None:
    """Every Compose stack resolves, and the local production rehearsal is production-like."""
    project = render({"project_name": "acme_service"})
    _run(["cp", "backend/.env.example", "backend/.env"], project)
    _run(["make", "-s", ".env.prod-local"], project)
    stacks = {
        "dev": ["-f", "docker-compose.dev.yml"],
        "frontend": ["-f", "docker-compose.frontend.yml"],
        "prod": ["--env-file", ".env.prod-local", "-f", "docker-compose.prod.yml"],
        "prod-local": [
            "--env-file",
            ".env.prod-local",
            "-f",
            "docker-compose.prod.yml",
            "-f",
            "docker-compose.prod-local.yml",
        ],
    }
    resolved = {
        name: yaml.safe_load(_run(["docker", "compose", *args, "config"], project))
        for name, args in stacks.items()
    }
    local = resolved["prod-local"]["services"]
    assert "traefik" not in local, "the rehearsal publishes ports instead of running Traefik"
    assert local["app"]["environment"]["ENVIRONMENT"] == "production"
    assert local["frontend"]["build"]["args"]["VITE_API_URL"] == "http://localhost:8000"
    images = {svc.get("image") for svc in resolved["prod"]["services"].values()}
    assert "acme_service_backend:dev" not in images, "production must not run the dev image"
    for path in project.glob("docker-compose*.yml"):
        assert "NEXT_PUBLIC" not in path.read_text(encoding="utf-8"), path.name
