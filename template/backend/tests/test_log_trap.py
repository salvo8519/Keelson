"""Log trap: secrets that pass through the application never reach the logs (Keelstone).

Known values (a password, a JWT, an API key, a provider key, a database password) are sent
through the logging paths the application uses: message, arguments, ``extra=`` fields, nested
structures and exception text, in both formats. The test fails if any of them is written.
"""

import base64
import io
import json
import logging
from collections.abc import Callable, Iterator
from uuid import UUID

import pytest

from app.core.logging import JsonFormatter, _AppHandler, scrub, setup_logging, without_secrets


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


# The canaries are built at run time, so that no secret-shaped literal sits in the source:
# the secret scan of the pipeline (gitleaks) would report them, and an exception for this
# file would weaken the scan of every generated project.
PASSWORD = "-".join(("Canary", "Passw0rd", "7f3a91"))
JWT = ".".join(
    _b64(part) for part in ('{"alg":"HS256"}', '{"sub":"canary-user"}', "signature-canary")
)
API_KEY = "key_" + "AbCdEfGhIjKl" + "." + _b64("secret-canary-secret-value-42x")
PROVIDER_KEY = "sk-" + "canary" + "providerkey" + "0123456789abcdef"
EMAIL = "canary.person@example.com"
SECRETS = {
    "password": PASSWORD,
    "jwt": JWT,
    "api key secret": API_KEY.split(".", 1)[1],
    "provider key": PROVIDER_KEY,
    "e-mail": EMAIL,
}


@pytest.fixture(params=["json", "text"])
def captured(request: pytest.FixtureRequest) -> Iterator[io.StringIO]:
    setup_logging(level="DEBUG", fmt=request.param)
    handler = next(h for h in logging.getLogger().handlers if isinstance(h, _AppHandler))
    stream = io.StringIO()
    handler.setStream(stream)
    yield stream
    setup_logging()


def _emit_everything() -> None:
    log = logging.getLogger("app.trap")
    log.info("login password=%s for %s", PASSWORD, EMAIL)
    log.info("Authorization: Bearer %s", JWT)
    log.info("api_key: %s", API_KEY)
    log.warning("provider rejected %s", PROVIDER_KEY)
    log.info(
        "event",
        extra={
            "password": PASSWORD,
            "refresh_token": JWT,
            "headers": {"Authorization": f"Bearer {JWT}", "X-API-Key": API_KEY},
            "to": [EMAIL],
            "payload": {"credentials": {"password": PASSWORD}},
        },
    )
    try:
        raise RuntimeError(f"request failed for {EMAIL} with {API_KEY} and Bearer {JWT}")
    except RuntimeError:
        log.exception("statement failed for token=%s", JWT)


def test_secrets_never_reach_the_logs(captured: io.StringIO) -> None:
    _emit_everything()
    written = captured.getvalue()
    assert written, "nothing was logged: the trap would pass vacuously"
    leaked = [name for name, value in SECRETS.items() if value in written]
    assert leaked == [], f"leaked to the logs: {leaked}\n{written}"


def test_usage_counters_are_not_mistaken_for_secrets() -> None:
    setup_logging(level="INFO", fmt="json")
    handler = next(h for h in logging.getLogger().handlers if isinstance(h, _AppHandler))
    stream = io.StringIO()
    handler.setStream(stream)
    try:
        logging.getLogger("app.trap").info("usage", extra={"input_tokens": 12, "token_type": "x"})
    finally:
        setup_logging()
    record = json.loads(stream.getvalue())
    assert (record["input_tokens"], record["token_type"]) == (12, "x")


def test_database_errors_do_not_carry_statement_values() -> None:
    """SQL errors would print the parameters (hashes, addresses, text) unless hidden."""
    from app.core.config import settings
    from app.db.session import engine, system_engine

    assert not settings.DEBUG
    assert engine.sync_engine.hide_parameters and system_engine.sync_engine.hide_parameters


# --- The pieces the trap relies on, one by one ------------------------------------------------


def _handler() -> _AppHandler:
    return next(h for h in logging.getLogger().handlers if isinstance(h, _AppHandler))


def _json_line(emit: Callable[[logging.Logger], None]) -> str:
    """What ``emit`` writes through the application's JSON handler."""
    setup_logging(level="INFO", fmt="json")
    stream = io.StringIO()
    _handler().setStream(stream)
    try:
        emit(logging.getLogger("app.trap"))
    finally:
        setup_logging()
    return stream.getvalue()


def test_fields_named_like_secrets_are_replaced_whatever_they_hold() -> None:
    assert scrub(12345, "api_key") == "[REDACTED]"
    assert scrub({"user": {"password": PASSWORD, "email": EMAIL, "age": 7}}) == {
        "user": {"password": "[REDACTED]", "email": "[EMAIL_REDACTED]", "age": 7}
    }
    assert scrub((EMAIL, 7)) == ["[EMAIL_REDACTED]", 7]
    assert scrub(7) == 7


@pytest.mark.parametrize(
    "name",
    [
        "password",
        "api_key",
        "secret_key",
        "SECRET_KEY",
        "aws_secret_access_key",
        "S3_SECRET_KEY",
        "secretAccessKey",
        "access_key",
        "encryption_key",
        "DATA_ENCRYPTION_KEYS",
        "private_keys",
        "passwords",
        "client_secrets",
        "private_key",
        "APIKey",
        "apikey",
        "api-key",
        "X-API-Key",
        "passphrase",
        "newPassword",
        "password_confirm",
        "hashed_password",
        "credentials_json",
        "credential",
        "client_secret",
        "webhookSecret",
        "refresh_token",
        "X-Auth-Token",
        "token",
        "Authorization",
        "Set-Cookie",
    ],
)
def test_names_of_secrets_are_recognised_in_any_spelling(name: str) -> None:
    assert scrub("value", name) == "[REDACTED]"
    assert without_secrets({name: "value"}) == {name: "[REDACTED]"}


# Names the application writes to logs and audit entries: an API key's public prefix ("key",
# "previous"), an e-mail template ("key"), token counters and types.
@pytest.mark.parametrize(
    "name",
    ["key", "keys", "key_id", "prefix", "previous", "token_type", "input_tokens", "max_tokens", "tokens", "monkey", "keyword"],
)
def test_harmless_names_stay_visible(name: str) -> None:
    assert scrub("value", name) == "value"
    assert without_secrets({name: "value"}) == {name: "value"}


def test_the_exception_is_written_redacted_in_json() -> None:
    def emit(log: logging.Logger) -> None:
        try:
            raise RuntimeError(f"request failed for {EMAIL}")
        except RuntimeError:
            log.exception("failed")

    record = json.loads(_json_line(emit))
    assert "RuntimeError: request failed for [EMAIL_REDACTED]" in record["exception"]


def test_json_lines_keep_any_value_and_any_language() -> None:
    org = UUID("12345678-1234-5678-1234-567812345678")
    line = _json_line(lambda log: log.info("Città aggiornata", extra={"org": org}))
    assert "Città aggiornata" in line, "non-ASCII text is written as is"
    assert json.loads(line)["org"] == str(org)


def test_json_is_the_default_format_and_text_is_available() -> None:
    setup_logging()
    assert isinstance(_handler().formatter, JsonFormatter)
    setup_logging(fmt="text")
    try:
        stream = io.StringIO()
        _handler().setStream(stream)
        logging.getLogger("app.trap").warning("plain")
        assert not isinstance(_handler().formatter, JsonFormatter)
        assert " WARNING app.trap [None] plain" in stream.getvalue()
    finally:
        setup_logging()
