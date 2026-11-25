"""A production start refuses development defaults for secrets (Keelson).

Evidence for configuration management: every secret with a development default must be set
before the application runs with ENVIRONMENT=production.
"""

import secrets
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import SECRETS_WHEN_DEPLOYED, Settings

DEFAULTED_SECRETS = (
    "SECRET_KEY", "API_KEY", "POSTGRES_PASSWORD", "POSTGRES_APP_PASSWORD", "DATA_ENCRYPTION_KEYS"
)
ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"


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
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_production_starts_with_real_secrets() -> None:
    assert _production().ENVIRONMENT == "production"


@pytest.mark.parametrize("name", DEFAULTED_SECRETS)
def test_production_refuses_a_development_default(name: str) -> None:
    default = Settings.model_fields[name].default
    with pytest.raises(ValidationError, match=name):
        _production(**{name: default})


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize("value", ["", "postgres", "change-me-in-production", "sk_test_xxx", " Password "])
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
