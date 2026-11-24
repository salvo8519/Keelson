"""A production start refuses development defaults for secrets (Keelson).

Evidence for configuration management: every secret with a development default must be set
before the application runs with ENVIRONMENT=production.
"""

import secrets

import pytest
from pydantic import ValidationError

from app.core.config import Settings

DEFAULTED_SECRETS = ("SECRET_KEY", "API_KEY", "POSTGRES_APP_PASSWORD", "DATA_ENCRYPTION_KEYS")


def _production(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "ENVIRONMENT": "production",
        "SECRET_KEY": secrets.token_hex(32),
        "API_KEY": secrets.token_hex(32),
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
