"""End-to-end test: render the default project and run its own checks and test suites."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import ROOT, Render

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


# Run in the generated backend: each secret of the Kubernetes manifest, alone on top of real
# values, must stop a production start. Prints the names that started anyway.
_K8S_SECRET_PROBE = """
import json, secrets, sys
from pydantic import ValidationError
from app.core.config import OPTIONAL_SECRETS_WHEN_DEPLOYED, SECRETS_WHEN_DEPLOYED, Settings

shipped = json.load(sys.stdin)
real = {n: secrets.token_hex(32) for n in SECRETS_WHEN_DEPLOYED if n in Settings.model_fields}
real |= {"DATA_ENCRYPTION_KEYS": [secrets.token_hex(32)], "CORS_ORIGINS": ["https://a.example"]}
checked = [*SECRETS_WHEN_DEPLOYED, *OPTIONAL_SECRETS_WHEN_DEPLOYED, "DATA_ENCRYPTION_KEYS"]
started = []
for name in [name for name in checked if name in shipped]:
    value = [shipped[name]] if name == "DATA_ENCRYPTION_KEYS" else shipped[name]
    try:
        Settings(_env_file=None, ENVIRONMENT="production", **{**real, name: value})
    except ValidationError:
        continue
    started.append(name)
print(json.dumps({"checked": [name for name in checked if name in shipped], "started": started}))
"""


def test_kubernetes_secret_stand_ins_do_not_start_in_production(render: Render) -> None:
    """The values of kubernetes/secret.yaml, deployed unchanged, are refused (Keelstone)."""
    project = render({"project_name": "acme_service"})
    backend = project / "backend"
    shipped = yaml.safe_load((project / "kubernetes" / "secret.yaml").read_text(encoding="utf-8"))
    _run(["uv", "sync", "--quiet"], backend)
    result = subprocess.run(
        ["uv", "run", "python", "-c", _K8S_SECRET_PROBE],
        cwd=backend,
        input=json.dumps(shipped["stringData"]),
        capture_output=True,
        text=True,
        check=True,
    )
    outcome = json.loads(result.stdout.strip().splitlines()[-1])
    expected = {
        "SECRET_KEY",
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "PROMETHEUS_AUTH_TOKEN",
        "S3_SECRET_KEY",
    }
    assert expected <= set(outcome["checked"])
    assert outcome["started"] == [], outcome


# Run in the generated backend: the secrets written by `make prod-local` start production.
_PROD_LOCAL_PROBE = """
import json, sys
from app.core.config import Settings

generated = json.load(sys.stdin)
values = {name: value for name, value in generated.items() if name in Settings.model_fields}
values["DATA_ENCRYPTION_KEYS"] = values["DATA_ENCRYPTION_KEYS"].split(",")
Settings(_env_file=None, ENVIRONMENT="production", CORS_ORIGINS=["https://a.example"], **values)
print(json.dumps(sorted(values)))
"""


def test_prod_local_secrets_start_in_production(render: Render) -> None:
    """Every secret `make prod-local` generates passes the deployed-secret rule (Keelstone)."""
    project = render({"project_name": "acme_service"})
    backend = project / "backend"
    _run(["make", "-s", ".env.prod-local"], project)
    generated = dict(
        line.split("=", 1)
        for line in (project / ".env.prod-local").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    )
    _run(["uv", "sync", "--quiet"], backend)
    result = subprocess.run(
        ["uv", "run", "python", "-c", _PROD_LOCAL_PROBE],
        cwd=backend,
        input=json.dumps(generated),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    checked = set(json.loads(result.stdout.strip().splitlines()[-1]))
    assert {"SECRET_KEY", "POSTGRES_PASSWORD", "S3_ACCESS_KEY", "S3_SECRET_KEY"} <= checked


def test_default_project_frontend_passes_its_checks(render: Render) -> None:
    """The official React frontend: Biome, translations, tsc and Vite against the Keelstone API."""
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
    # Keelstone hardening: secrets readable by their owner only, the rehearsal on the loopback
    # interface, the Valkey password off every command line, forwarded headers from the proxy.
    assert (project / ".env.prod-local").stat().st_mode & 0o077 == 0
    for name in ("app", "frontend"):
        assert {port["host_ip"] for port in local[name]["ports"]} == {"127.0.0.1"}, name
    questions = next(yaml.safe_load_all((ROOT / "copier.yml").read_text(encoding="utf-8")))
    proxy_subnet = questions["proxy_network_subnet"]["default"]
    password = dict(
        line.split("=", 1)
        for line in (project / ".env.prod-local").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    )["REDIS_PASSWORD"]
    for name in ("prod", "prod-local"):
        redis = resolved[name]["services"]["redis"]
        assert password not in json.dumps([redis["command"], redis["healthcheck"]]), name
        app = resolved[name]["services"]["app"]
        assert app["environment"]["FORWARDED_ALLOW_IPS"] == proxy_subnet, name
        assert "--forwarded-allow-ips" not in " ".join(app["command"]), name
    incomplete = project / ".env.incomplete"
    incomplete.write_text(
        "".join(
            line + "\n"
            for line in (project / ".env.prod-local").read_text(encoding="utf-8").splitlines()
            if not line.startswith("ACME_EMAIL=")
        ),
        encoding="utf-8",
    )
    refused = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(incomplete),
            "-f",
            "docker-compose.prod.yml",
            "config",
        ],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode != 0 and "ACME_EMAIL is required" in refused.stderr
    assert local["app"]["environment"]["ENVIRONMENT"] == "production"
    assert local["frontend"]["build"]["args"]["VITE_API_URL"] == "http://localhost:8000"
    images = {svc.get("image") for svc in resolved["prod"]["services"].values()}
    assert "acme_service_backend:dev" not in images, "production must not run the dev image"
    for path in project.glob("docker-compose*.yml"):
        assert "NEXT_PUBLIC" not in path.read_text(encoding="utf-8"), path.name
    # Documents go to the Garage service: pinned image, bootstrap before the API, S3 settings
    # and secrets from the environment, never from the committed configuration.
    for name in ("dev", "prod", "prod-local"):
        services = resolved[name]["services"]
        assert re.fullmatch(r"dxflrs/garage:v\d+\.\d+\.\d+", services["garage"]["image"]), name
        assert services["app"]["depends_on"]["garage-init"]["condition"] == (
            "service_completed_successfully"
        )
        assert services["app"]["environment"]["S3_ENDPOINT"] == "http://garage:3900", name
        assert services["app"]["environment"]["STORAGE_BACKEND"] == "s3", name
    local_secrets = local["garage"]["environment"]
    assert len(local_secrets["GARAGE_RPC_SECRET"]) == 64, "generated for the rehearsal"
    assert re.fullmatch(r"GK[0-9a-f]{24}", local["app"]["environment"]["S3_ACCESS_KEY"])
    secret = local["app"]["environment"]["S3_SECRET_KEY"]
    assert local["garage-init"]["environment"]["S3_SECRET_KEY"] == secret
    garage_toml = (project / "garage" / "garage.toml").read_text(encoding="utf-8")
    assert "rpc_secret =" not in garage_toml and "admin_token =" not in garage_toml
