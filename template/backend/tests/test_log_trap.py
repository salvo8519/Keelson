"""Log trap: secrets that pass through the application never reach the logs (Keelson).

Known values (a password, a JWT, an API key, a provider key, a database password) are sent
through the logging paths the application uses: message, arguments, ``extra=`` fields, nested
structures and exception text, in both formats. The test fails if any of them is written.
"""

import io
import json
import logging
from collections.abc import Iterator

import pytest

from app.core.logging import _AppHandler, setup_logging

PASSWORD = "Canary-Passw0rd-7f3a91"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjYW5hcnktdXNlciJ9.c2lnbmF0dXJlLWNhbmFyeQ"
API_KEY = "key_AbCdEfGhIjKl.c2VjcmV0LWNhbmFyeS1zZWNyZXQtdmFsdWUtNDJ4"
PROVIDER_KEY = "sk-canaryproviderkey0123456789abcdef"
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
