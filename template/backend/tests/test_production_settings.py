"""A production start refuses development defaults for secrets (Keelstone).

Evidence for configuration management: every secret with a development default must be set
before the application runs with ENVIRONMENT=production.
"""

import secrets
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import (
    MAX_DEPLOYED_ACCESS_TOKEN_MINUTES,
    MIN_DEPLOYED_SECRET_DISTINCT_CHARACTERS,
    MIN_DEPLOYED_SECRET_LENGTH,
    OPTIONAL_SECRETS_WHEN_DEPLOYED,
    PUBLISHED_DEVELOPMENT_SECRETS,
    SECRETS_WHEN_DEPLOYED,
    Settings,
    is_placeholder_secret,
)

DEFAULTED_SECRETS = tuple(
    name
    for name in (
        "SECRET_KEY",
        "API_KEY",
        "POSTGRES_PASSWORD",
        "POSTGRES_APP_PASSWORD",
        "DATA_ENCRYPTION_KEYS",
        "PROMETHEUS_AUTH_TOKEN",
    )
    if name in Settings.model_fields
)
ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
# Published with the project, outside the backend image: the settings keep a copy of its values.
GARAGE_DEVELOPMENT_ENV = Path(__file__).resolve().parents[2] / "garage" / "development.env"
DEPLOYED_SECRETS = tuple(name for name in SECRETS_WHEN_DEPLOYED if name in Settings.model_fields)
OPTIONAL_SECRETS = tuple(name for name in OPTIONAL_SECRETS_WHEN_DEPLOYED if name in Settings.model_fields)


def _example_secrets() -> dict[str, str]:
    """The secrets as .env.example writes them: copied unchanged, they must not start."""
    values = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name in SECRETS_WHEN_DEPLOYED and name in Settings.model_fields and value:
            values[name] = value.split("#")[0].strip()
    return values


def _production(environment: str = "production", **overrides: object) -> Settings:
    values: dict[str, object] = {
        "ENVIRONMENT": environment,
        "SECRET_KEY": secrets.token_hex(32),
        "API_KEY": secrets.token_hex(32),
        "POSTGRES_PASSWORD": secrets.token_hex(16),
        "POSTGRES_APP_PASSWORD": secrets.token_hex(16),
        "DATA_ENCRYPTION_KEYS": [secrets.token_hex(32)],
        "CORS_ORIGINS": ["https://app.example.com"],
        **overrides,
    }
    if "PROMETHEUS_AUTH_TOKEN" in Settings.model_fields:
        values.setdefault("PROMETHEUS_AUTH_TOKEN", secrets.token_hex(32))
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_production_starts_with_real_secrets() -> None:
    assert _production().ENVIRONMENT == "production"


@pytest.mark.parametrize("name", DEFAULTED_SECRETS)
def test_production_refuses_a_development_default(name: str) -> None:
    default = Settings.model_fields[name].default
    with pytest.raises(ValidationError, match=name):
        _production(**{name: default})


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize(
    "value",
    [
        "",
        "postgres",
        "change-me-in-production",
        "sk_test_xxx",
        " Password ",
        # The stand-ins of the Kubernetes secret and of other examples, in any case and separator.
        "CHANGE_ME_IN_PRODUCTION",
        "CHANGE_ME",
        "change_this",
        "Change Me",
    ],
)
def test_deployed_environments_refuse_stand_in_database_passwords(environment: str, value: str) -> None:
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        _production(environment, POSTGRES_PASSWORD=value)


def test_the_values_of_env_example_do_not_start_in_production() -> None:
    examples = _example_secrets()
    assert "POSTGRES_PASSWORD" in examples, "the example file lists the database password"
    for name, value in examples.items():
        with pytest.raises(ValidationError, match=name):
            _production(**{name: [value] if name == "DATA_ENCRYPTION_KEYS" else value})


@pytest.mark.parametrize("environment", ["local", "development"])
def test_development_accepts_stand_ins(environment: str) -> None:
    settings = _production(environment, POSTGRES_PASSWORD="postgres", API_KEY="change-me-in-production")
    assert settings.ENVIRONMENT == environment


@pytest.mark.parametrize("value", ["CHANGE_ME_IN_PRODUCTION", "CHANGE_ME", "change_this", "change.me"])
def test_stand_ins_are_recognised_in_any_spelling(value: str) -> None:
    assert is_placeholder_secret(value)


def test_random_secrets_are_not_stand_ins() -> None:
    assert not is_placeholder_secret(secrets.token_hex(32))
    assert not is_placeholder_secret(secrets.token_urlsafe(32).replace("x", "y"))


def _env_values(path: Path) -> set[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line.partition("=")[2].strip() for line in lines if "=" in line and not line.startswith("#")}


def test_the_published_development_secrets_are_those_of_the_garage_file() -> None:
    """The backend image lacks garage/development.env: its copy must follow the file."""
    assert PUBLISHED_DEVELOPMENT_SECRETS == _env_values(GARAGE_DEVELOPMENT_ENV)


@pytest.mark.parametrize("name", [*DEPLOYED_SECRETS, *OPTIONAL_SECRETS])
@pytest.mark.parametrize("value", sorted(PUBLISHED_DEVELOPMENT_SECRETS))
def test_deployed_environments_refuse_the_published_development_secrets(name: str, value: str) -> None:
    with pytest.raises(ValidationError, match=name):
        _production(**{name: value})


@pytest.mark.parametrize("value", ["Development_Only", " DEVELOPMENT ONLY ", "development.only"])
def test_published_development_secrets_are_refused_in_any_case_and_separator(value: str) -> None:
    with pytest.raises(ValidationError, match="API_KEY"):
        _production(API_KEY=value)


def test_optional_secrets_may_be_left_empty() -> None:
    assert _production(**dict.fromkeys(OPTIONAL_SECRETS, "")).ENVIRONMENT == "production"


@pytest.mark.parametrize("name", [*DEPLOYED_SECRETS, *OPTIONAL_SECRETS])
@pytest.mark.parametrize(
    "value",
    [
        "1",
        "x",
        "a",
        "0" * 64,
        "ab" * 32,
        # One character short of the minimum, every character different.
        "abcdefghijklmnopqrstuvwxyz0123456789"[: MIN_DEPLOYED_SECRET_LENGTH - 1],
        # Long enough, one distinct character short of the minimum.
        ("abcdefghijklmnopqrstuvwxyz"[: MIN_DEPLOYED_SECRET_DISTINCT_CHARACTERS - 1] * 64)[:64],
    ],
)
def test_deployed_environments_refuse_weak_secrets(name: str, value: str) -> None:
    with pytest.raises(ValidationError, match=name):
        _production(**{name: value})


def test_weak_data_encryption_keys_are_refused() -> None:
    with pytest.raises(ValidationError, match="DATA_ENCRYPTION_KEYS"):
        _production(DATA_ENCRYPTION_KEYS=["0" * 64])


def test_secrets_at_the_minimum_strength_start() -> None:
    value = "abcdefghijklmnopqrstuvwxyz"[:MIN_DEPLOYED_SECRET_DISTINCT_CHARACTERS]
    value = (value * MIN_DEPLOYED_SECRET_LENGTH)[:MIN_DEPLOYED_SECRET_LENGTH]
    names = [name for name in (*DEPLOYED_SECRETS, *OPTIONAL_SECRETS) if name != "SECRET_KEY"]
    assert _production(**dict.fromkeys(names, value)).ENVIRONMENT == "production"


@pytest.mark.parametrize(
    "value",
    [
        secrets.token_hex(32),  # openssl rand -hex 32, the documented generator
        secrets.token_hex(24),  # make prod-local, database and Valkey passwords
        "GK" + secrets.token_hex(12),  # make prod-local, the Garage key
        # The shape of an AWS access key id, built at run time: no key-shaped literal in the code.
        "AKIA" + secrets.token_hex(8).upper(),
    ],
)
def test_the_generators_of_the_project_satisfy_the_minimum(value: str) -> None:
    assert len(value) >= MIN_DEPLOYED_SECRET_LENGTH
    assert len(set(value)) >= MIN_DEPLOYED_SECRET_DISTINCT_CHARACTERS


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_environments_refuse_debug(environment: str) -> None:
    with pytest.raises(ValidationError, match="DEBUG"):
        _production(environment, DEBUG=True)


@pytest.mark.skipif(
    "PROMETHEUS_AUTH_TOKEN" not in Settings.model_fields, reason="metrics are not enabled"
)
def test_deployed_metrics_need_a_token() -> None:
    """Without a token the metrics endpoint is public on the API port."""
    with pytest.raises(ValidationError, match="PROMETHEUS_AUTH_TOKEN"):
        _production(PROMETHEUS_AUTH_TOKEN="")


@pytest.mark.skipif("ALGORITHM" not in Settings.model_fields, reason="no JWT in this project")
@pytest.mark.parametrize("algorithm", ["none", "RS256", "hs256"])
def test_only_hmac_signing_algorithms_are_accepted(algorithm: str) -> None:
    with pytest.raises(ValidationError, match="ALGORITHM"):
        _production(ALGORITHM=algorithm)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_environments_refuse_long_lived_access_tokens(environment: str) -> None:
    """An access token is checked against its session only by its version: it must be short."""
    assert _production(environment, ACCESS_TOKEN_EXPIRE_MINUTES=MAX_DEPLOYED_ACCESS_TOKEN_MINUTES)
    with pytest.raises(ValidationError, match="ACCESS_TOKEN_EXPIRE_MINUTES"):
        _production(environment, ACCESS_TOKEN_EXPIRE_MINUTES=MAX_DEPLOYED_ACCESS_TOKEN_MINUTES + 1)


def test_env_example_access_token_lifetime_is_the_default_and_within_the_limit() -> None:
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    value = next(line.partition("=")[2] for line in lines if line.startswith("ACCESS_TOKEN_EXPIRE_MINUTES="))
    assert int(value) == Settings.model_fields["ACCESS_TOKEN_EXPIRE_MINUTES"].default
    assert int(value) <= MAX_DEPLOYED_ACCESS_TOKEN_MINUTES
