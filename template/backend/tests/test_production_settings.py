"""A production start refuses development defaults for secrets (Keelstone).

Evidence for configuration management: every secret with a development default must be set
before the application runs with ENVIRONMENT=production.
"""

import base64
import re
import secrets
import string
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import (
    MAX_DEPLOYED_ACCESS_TOKEN_MINUTES,
    DEPLOYED_KEY_IDS,
    MIN_DEPLOYED_KEY_ID_LENGTH,
    MIN_DEPLOYED_SECRET_DISTINCT_CHARACTERS,
    MIN_DEPLOYED_SECRET_LENGTH,
    MIN_PROJECT_SECRET_WORD_LENGTH,
    MIN_SIGNING_KEY_LENGTH,
    OPTIONAL_SECRETS_WHEN_DEPLOYED,
    PROJECT_SECRET_WORD,
    PUBLISHED_DEVELOPMENT_SECRETS,
    SECRETS_NOT_CHECKED_WHEN_DEPLOYED,
    SECRETS_WHEN_DEPLOYED,
    WEAK_SECRET_RULE,
    Settings,
    is_placeholder_secret,
    is_weak_secret,
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
    checked = (*SECRETS_WHEN_DEPLOYED, *OPTIONAL_SECRETS_WHEN_DEPLOYED)
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name in checked and name in Settings.model_fields and value:
            values[name] = value.split("#")[0].strip()
    return values


def _refused_by_the_rule(name: str) -> str:
    """The refusal of the deployed-secret rule for this setting alone, as a pattern."""
    return rf"(?<![A-Z0-9_]){name} {re.escape(WEAK_SECRET_RULE)}"


def _assert_refused_by_the_rule(name: str, value: str) -> None:
    """The rule refuses the value, and the start fails with the rule's own message.

    SECRET_KEY has a stricter length check of its own (MIN_SIGNING_KEY_LENGTH), which runs
    first and stops the validation: for a shorter value that message is the one shown, and
    ``is_weak_secret`` proves the rule.
    """
    assert is_weak_secret(value), value
    if name == "SECRET_KEY" and len(value.strip()) < MIN_SIGNING_KEY_LENGTH:
        match = f"SECRET_KEY must be at least {MIN_SIGNING_KEY_LENGTH} characters"
    else:
        match = _refused_by_the_rule(name)
    with pytest.raises(ValidationError, match=match):
        _production(**{name: value})


def _production(environment: str = "production", **overrides: object) -> Settings:
    values: dict[str, object] = {
        "ENVIRONMENT": environment,
        "SECRET_KEY": secrets.token_hex(32),
        "API_KEY": secrets.token_hex(32),
        "POSTGRES_PASSWORD": secrets.token_hex(24),
        "POSTGRES_APP_PASSWORD": secrets.token_hex(24),
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
    _assert_refused_by_the_rule(name, value)


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
    _assert_refused_by_the_rule(name, value)


def test_weak_data_encryption_keys_are_refused() -> None:
    with pytest.raises(ValidationError, match=_refused_by_the_rule("DATA_ENCRYPTION_KEYS")):
        _production(DATA_ENCRYPTION_KEYS=["0" * 64])


# Typed values long and varied enough that only the last checks of the rule refuse them: words
# (look-alike substitutions undone), published values, the project's name, runs of neighbouring
# characters, repetitions, doubled characters. Built at run time where they look like secrets
# (the pipeline's secret scan).
GUESSABLE_SECRETS = [
    "-".join(("password", "password", "password", "12345")),
    "_".join(("P@ssw0rd", "P@ssw0rd", "P@ssw0rd", "1234567")),
    "abcdefghijklmnopqrstuvwxyz012345",
    "0123456789abcdef0123456789abcdef",
    "qwertyuiopasdfghjklzxcvbnm123456",
    "fedcba9876543210fedcba9876543210",
    "1q2w3e4r5t6y7u8i9o0p1q2w3e4r5t6y",
    "development-only-development-only",
    f"{PROJECT_SECRET_WORD}-production-secret-key",
    "-".join(("Admin", "Admin", "7q2z", "Kx9w", "4r", "letmein")),
    "-".join(("s3cr3t", "s3cr3t", "s3cr3t", "key", "2025", "01")),
    "_".join(("adm1n", "adm1n", "adm1n", "adm1n", "2025!!!!")),
    "testtesttesttesttest123456789012",
    "dummydummydummy-1234567890123456",
    "changeit-changeit-changeit-chang",
    "demo-demo-demo-demo-demo-2025-01",
    # Stand-in phrases (third review).
    "your-api-key-goes-here-right-now",
    "replace_me_with_a_real_key_please",
    "insecure-dev-key-please-change-it",
    # Doubled characters (third review).
    "".join(char * 2 for char in "zyxwvu12kmpqrs34"),
    "".join(char * 2 for char in "abcd1234efgh5678"),
]
# Shorter guessable values, refused by the length alone since the minimum is 32 characters.
SHORT_GUESSABLE_SECRETS = [
    "password12345678",
    "".join(("P@ssw0rd", "123456789")),
    "-".join(("s3cr3t", "s3cr3t", "key", "01")),
    "_".join(("adm1n", "adm1n", "2025!")),
    "testtesttest12345678",
    "dummydummy123456",
    "changeit-changeit",
    "demo-demo-demo-2025",
    "1q2w3e4r5t6y7u8i9o",
    "zzyyxxwwvvuu1122",
    "aabbccdd11223344",
    "your-api-key-goes-here",
    "replace_me_with_a_real_key",
    "insecure-dev-key-please-change",
]


@pytest.mark.parametrize("value", GUESSABLE_SECRETS)
def test_guessable_secrets_are_weak(value: str) -> None:
    assert len(value) >= MIN_DEPLOYED_SECRET_LENGTH
    assert len(set(value)) >= MIN_DEPLOYED_SECRET_DISTINCT_CHARACTERS
    _assert_refused_by_the_rule("API_KEY", value)


@pytest.mark.parametrize("value", SHORT_GUESSABLE_SECRETS)
def test_short_guessable_secrets_are_weak(value: str) -> None:
    _assert_refused_by_the_rule("API_KEY", value)


def _strong_but_short(length: int) -> str:
    """A random value that every check of the rule but the length accepts."""
    while is_weak_secret(value := _random(_BASE62, length), min_length=length):
        pass
    return value


@pytest.mark.parametrize("name", [name for name in (*DEPLOYED_SECRETS, *OPTIONAL_SECRETS) if name not in DEPLOYED_KEY_IDS])
@pytest.mark.parametrize("length", [16, MIN_DEPLOYED_SECRET_LENGTH - 1])
def test_secrets_of_16_to_31_characters_are_refused(name: str, length: int) -> None:
    """The minimum is 32 for every secret but the access key ids: 16 characters, accepted
    before, are refused, with the rule's own message."""
    _assert_refused_by_the_rule(name, _strong_but_short(length))


def test_the_project_name_is_refused_in_a_secret() -> None:
    value = f"{PROJECT_SECRET_WORD}-{PROJECT_SECRET_WORD}-" + _random(_BASE62, 20)
    if len(PROJECT_SECRET_WORD) >= MIN_PROJECT_SECRET_WORD_LENGTH:
        _assert_refused_by_the_rule("API_KEY", value)
    else:
        # A short name would refuse random values by chance: it is not checked.
        assert not is_weak_secret(value)


@pytest.mark.parametrize("value", ["", "x", "0" * 64, "password", "abcdefghabcdefgh"])
def test_secret_key_weak_values_are_refused_by_one_check_or_the_other(value: str) -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _production(SECRET_KEY=value)


def test_secrets_at_the_minimum_strength_start() -> None:
    # 32 characters, eight distinct, few neighbours on the keyboard, no repeated piece.
    value = "aqzmwkxpzkxpmwqapxwakqmzmpaxkwzq"
    assert (len(value), len(set(value))) == (MIN_DEPLOYED_SECRET_LENGTH, MIN_DEPLOYED_SECRET_DISTINCT_CHARACTERS)
    assert not is_weak_secret(value)
    names = [name for name in (*DEPLOYED_SECRETS, *OPTIONAL_SECRETS) if name != "SECRET_KEY"]
    assert _production(**dict.fromkeys(names, value)).ENVIRONMENT == "production"


def _random(alphabet: str, length: int) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(length))


_BASE62 = string.ascii_letters + string.digits
# Secrets of the generators of the project and of the providers, built at run time.
SECRET_FORMATS: dict[str, Callable[[], str]] = {
    "openssl rand -hex 32 (documented generator)": lambda: secrets.token_hex(32),
    "make prod-local passwords (token_hex(24))": lambda: secrets.token_hex(24),
    "32 hexadecimal digits (openssl rand -hex 16)": lambda: secrets.token_hex(16),
    "32 random letters and digits": lambda: _random(_BASE62, 32),
    "urlsafe token": lambda: secrets.token_urlsafe(32),
    "base64 of 32 bytes": lambda: base64.b64encode(secrets.token_bytes(32)).decode(),
    "stripe secret key": lambda: "sk_live_" + _random(_BASE62, 99),
    "stripe webhook secret": lambda: "whsec_" + _random(_BASE62, 32),
    "aws secret access key": lambda: _random(_BASE62 + "+/", 40),
}
# Access key ids, checked with their own minimum (DEPLOYED_KEY_IDS).
KEY_ID_FORMATS: dict[str, Callable[[], str]] = {
    "garage key (make prod-local)": lambda: "GK" + secrets.token_hex(12),
    "aws access key id": lambda: "AKIA" + _random(string.ascii_uppercase + "234567", 16),
}


@pytest.mark.parametrize("fmt", sorted(SECRET_FORMATS))
def test_generated_and_provider_secrets_are_never_refused(fmt: str) -> None:
    """A real key must start: no check of the rule may refuse one by chance."""
    refused = [value for value in (SECRET_FORMATS[fmt]() for _ in range(3000)) if is_weak_secret(value)]
    assert refused == []


@pytest.mark.parametrize("fmt", sorted(KEY_ID_FORMATS))
def test_generated_and_provider_key_ids_are_never_refused(fmt: str) -> None:
    refused = [
        value
        for value in (KEY_ID_FORMATS[fmt]() for _ in range(3000))
        if is_weak_secret(value, min_length=MIN_DEPLOYED_KEY_ID_LENGTH)
    ]
    assert refused == []


@pytest.mark.parametrize("name", sorted(DEPLOYED_KEY_IDS & set(OPTIONAL_SECRETS)))
def test_access_key_ids_have_their_own_minimum(name: str) -> None:
    assert _production(**{name: KEY_ID_FORMATS["aws access key id"]()}).ENVIRONMENT == "production"
    with pytest.raises(ValidationError, match=_refused_by_the_rule(name)):
        _production(**{name: _random(_BASE62, MIN_DEPLOYED_KEY_ID_LENGTH - 1)})


def test_a_well_known_word_inside_a_random_key_is_not_refused() -> None:
    """ "whsec_" followed by "ret" spells "secret": a small share of the key, so it starts."""
    assert not is_weak_secret("whsec_" + "ret" + _random(_BASE62, 29))
    assert not is_weak_secret(_random(_BASE62, 20) + "password" + _random(_BASE62, 20))


@pytest.mark.parametrize("vendor", ["stripe secret key", "base64 of 32 bytes", "aws secret access key"])
def test_three_x_inside_a_real_key_is_not_a_stand_in(vendor: str) -> None:
    value = SECRET_FORMATS[vendor]()
    middle = len(value) // 2
    value = value[:middle] + "xxx" + value[middle:]
    assert not is_placeholder_secret(value)
    assert not is_weak_secret(value)


@pytest.mark.parametrize(
    "value", ["sk_test_xxx", "whsec_xxx", "re_xxx", "pk_test_xxx", "xxx", "XXXXXXXX", "pnu_" + "x" * 20, "token.xxxx"]
)
def test_x_stand_ins_are_refused(value: str) -> None:
    assert is_placeholder_secret(value)


def test_the_deployed_secret_lists_are_the_expected_ones() -> None:
    """Written out, so that removing an entry from a list fails a test."""
    assert SECRETS_WHEN_DEPLOYED == (
        "SECRET_KEY",
        "API_KEY",
        "POSTGRES_PASSWORD",
        "POSTGRES_APP_PASSWORD",
        "CHANNEL_ENCRYPTION_KEY",
        "REDIS_PASSWORD",
        "ARQ_REDIS_PASSWORD",
        "PROMETHEUS_AUTH_TOKEN",
    )
    assert OPTIONAL_SECRETS_WHEN_DEPLOYED == (
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "S3_RAG_ACCESS_KEY",
        "S3_RAG_SECRET_KEY",
        "IDP_SHARED_SECRET",
        "QDRANT_API_KEY",
        "SLACK_SIGNING_SECRET",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "RESEND_API_KEY",
    )


def test_every_setting_named_like_a_secret_is_checked_or_exempted() -> None:
    """A new secret setting must join a list of the rule or be exempted with a reason."""
    from app.core.logging import is_secret_name

    accounted = {*SECRETS_WHEN_DEPLOYED, *OPTIONAL_SECRETS_WHEN_DEPLOYED, *SECRETS_NOT_CHECKED_WHEN_DEPLOYED}
    accounted.add("DATA_ENCRYPTION_KEYS")
    unaccounted = sorted(name for name in Settings.model_fields if is_secret_name(name) and name not in accounted)
    assert unaccounted == []
    assert not set(SECRETS_NOT_CHECKED_WHEN_DEPLOYED) & {*SECRETS_WHEN_DEPLOYED, *OPTIONAL_SECRETS_WHEN_DEPLOYED}
    assert all(SECRETS_NOT_CHECKED_WHEN_DEPLOYED.values()), "every exemption states its reason"


def test_the_stand_ins_of_optional_secrets_in_env_example_do_not_start() -> None:
    """For example the Stripe stand-ins ("..._xxx") where billing is part of the project."""
    examples = _example_secrets()
    for name in [name for name in OPTIONAL_SECRETS if name in examples]:
        _assert_refused_by_the_rule(name, examples[name])


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


@pytest.mark.parametrize("document", ["ENV_VARS.md", "docs/en/guides/configuration.md"])
def test_the_documented_minimums_are_those_of_the_rule(document: str) -> None:
    text = " ".join((Path(__file__).resolve().parents[2] / document).read_text(encoding="utf-8").split())
    assert f"at least {MIN_DEPLOYED_SECRET_LENGTH} characters, {MIN_DEPLOYED_SECRET_DISTINCT_CHARACTERS} of them different" in text
    assert f"need {MIN_SIGNING_KEY_LENGTH} characters" in text
    assert f"need at least {MIN_DEPLOYED_KEY_ID_LENGTH} characters" in text


# asyncpg and libpq prepare these differently (SASLprep): one driver could not sign in.
NON_ASCII_DATABASE_PASSWORDS = ["x\u0300", "\u1d5b", "\u2011\u2097\u2117", "caf\u00e9"]


@pytest.mark.parametrize("name", [name for name in ("POSTGRES_PASSWORD", "POSTGRES_APP_PASSWORD") if name in Settings.model_fields])
@pytest.mark.parametrize("value", [*NON_ASCII_DATABASE_PASSWORDS, "tab\there", " leading", "trailing "])
@pytest.mark.parametrize("environment", ["local", "production"])
def test_database_passwords_are_printable_ascii_without_surrounding_spaces(name: str, value: str, environment: str) -> None:
    value = value + secrets.token_hex(16) if not value.endswith(" ") else secrets.token_hex(16) + value
    with pytest.raises(ValidationError, match=rf"{name} must (be printable ASCII|not begin or end with a space)"):
        _production(environment, **{name: value})


@pytest.mark.skipif("POSTGRES_APP_USER" not in Settings.model_fields, reason="no application login")
def test_the_application_login_differs_from_the_owner() -> None:
    with pytest.raises(ValidationError, match="POSTGRES_APP_USER must differ from POSTGRES_USER"):
        _production(POSTGRES_APP_USER=Settings.model_fields["POSTGRES_USER"].default)
