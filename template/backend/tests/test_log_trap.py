"""Log trap: secrets that pass through the application never reach the logs (Keelstone).

Known values (a password, a JWT, an API key, a provider key, a database password) are sent
through the logging paths the application uses: message, arguments, ``extra=`` fields, nested
structures and exception text, in both formats. The test fails if any of them is written.
"""

import base64
import dataclasses
import io
import json
import logging
import time
from collections.abc import Callable, Iterator
from types import MappingProxyType
from urllib.parse import quote
from uuid import UUID

import pytest
from pydantic import BaseModel

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


# A value no text pattern redacts: only the name of its field can hide it.
NAMED_CANARY = "-".join(("named", "field", "canary", "4c1d"))
# Names the second review found written in clear: plurals and fused forms, suffixes after the
# secret word, abbreviations.
LEAKING_NAMES = [
    "refresh_tokens",
    "access_tokens",
    "api_tokens",
    "accesstoken",
    "authtoken",
    "refreshtoken",
    "apikeys",
    "sshkey",
    "PGPASSWORD",
    "api_key_v2",
    "accessToken2",
    "private_key_pem",
    "encryption_key_v1",
    "apiKeyHash",
    "pwd",
    "passcode",
    "otp",
    # Second review.
    "authorization_header",
    "jwt",
    "bearer",
    "creds",
    "totp",
    "mfa_code",
    "recovery_codes",
    "backup_codes",
    "csrftoken",
    "xsrf",
    "tokenhash",
    "keyhash",
    "refreshtokenhash",
    # Third review.
    "auth_code",
    "reset_code",
    "oauth_code",
    "code_verifier",
    "client_assertion",
    "session_id",
    "sessionId",
    "SENTRY_DSN",
]


@pytest.mark.parametrize("name", LEAKING_NAMES)
def test_secret_names_of_every_shape_stay_out_of_the_logs(name: str) -> None:
    line = _json_line(lambda log: log.info("event", extra={name: NAMED_CANARY}))
    assert NAMED_CANARY not in line
    assert json.loads(line)[name] == "[REDACTED]"


@pytest.mark.parametrize("name", LEAKING_NAMES)
def test_secret_names_of_every_shape_stay_out_of_audit_details(name: str) -> None:
    assert without_secrets({"change": {name: NAMED_CANARY}}) == {"change": {name: "[REDACTED]"}}


class _Credentials(BaseModel):
    email: str
    password: str


@dataclasses.dataclass
class _Connection:
    host: str
    api_key: str


def test_a_model_in_extra_is_written_without_its_secret_fields() -> None:
    line = _json_line(
        lambda log: log.info(
            "event", extra={"user": _Credentials(email="a", password=NAMED_CANARY)}
        )
    )
    assert NAMED_CANARY not in line
    assert json.loads(line)["user"] == {"email": "a", "password": "[REDACTED]"}


def test_a_dataclass_in_extra_is_written_without_its_secret_fields() -> None:
    line = _json_line(
        lambda log: log.info("event", extra={"target": _Connection(host="h", api_key=NAMED_CANARY)})
    )
    assert NAMED_CANARY not in line
    assert json.loads(line)["target"] == {"host": "h", "api_key": "[REDACTED]"}


def test_models_dataclasses_and_mappings_in_audit_details_lose_their_secret_fields() -> None:
    details = {
        "user": _Credentials(email="a", password=NAMED_CANARY),
        "target": _Connection(host="h", api_key=NAMED_CANARY),
        "headers": MappingProxyType({"X-API-Key": NAMED_CANARY, "Accept": "text/plain"}),
    }
    assert without_secrets(details) == {
        "user": {"email": "a", "password": "[REDACTED]"},
        "target": {"host": "h", "api_key": "[REDACTED]"},
        "headers": {"X-API-Key": "[REDACTED]", "Accept": "text/plain"},
    }


def test_header_pairs_are_read_as_names_and_values() -> None:
    headers = [("Authorization", "Basic " + NAMED_CANARY), ("Accept", "text/plain")]
    raw = [(b"cookie", ("session=" + NAMED_CANARY).encode())]
    line = _json_line(lambda log: log.info("event", extra={"headers": headers, "raw": raw}))
    assert NAMED_CANARY not in line
    assert json.loads(line)["headers"] == [
        ["Authorization", "[REDACTED]"],
        ["Accept", "text/plain"],
    ]
    assert without_secrets(headers) == [["Authorization", "[REDACTED]"], ["Accept", "text/plain"]]


def test_two_addresses_are_not_mistaken_for_a_name_and_a_value() -> None:
    other = "second.person@example.com"
    assert scrub([EMAIL, other]) == ["[EMAIL_REDACTED]", "[EMAIL_REDACTED]"]


# Names the application writes to logs and audit entries (every ``extra=`` and ``record_audit``
# call of the template): an API key's public prefix ("key", "previous"), an e-mail template
# ("key"), token counters and types, identifiers, and names about a secret rather than of it.
@pytest.mark.parametrize(
    "name",
    [
        "key",
        "keys",
        "key_id",
        "prefix",
        "previous",
        "scopes",
        "missing",
        "reason",
        "grace_seconds",
        "expires_in",
        "target_email",
        "acting_admin_id",
        "workload",
        "ci_subject",
        "organization_id",
        "error_code",
        "status_code",
        "details",
        "event_id",
        "checkout_session_id",
        "client_assertion_type",
        "message_id",
        "retry_after_seconds",
        "token_type",
        "token_usage",
        "token_url",
        "token_endpoint",
        "api_key_prefix",
        "api_key_header",
        "cookie_name",
        "authorization_url",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "max_tokens",
        "tokens",
        "tokens_used",
        "monkey",
        "keyword",
        # Settings and flags named after a secret without holding one (second review).
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "REFRESH_TOKEN_EXPIRE_MINUTES",
        "CORS_ALLOW_CREDENTIALS",
        "GOOGLE_DRIVE_CREDENTIALS_FILE",
        "jwt_algorithm",
        "mfa_enabled",
        "error_code",
    ],
)
def test_harmless_names_stay_visible(name: str) -> None:
    assert scrub("value", name) == "value"
    assert without_secrets({name: "value"}) == {name: "value"}


# The price of a broad rule, stated in is_secret_name: these are hidden although they are not
# secrets. A change that makes one visible must make sure no secret becomes visible with it.
@pytest.mark.parametrize(
    "name",
    ["object_key", "idempotency_key", "cache_key", "primary_key", "public_key", "page_token"],
)
def test_accepted_regressions_are_hidden(name: str) -> None:
    assert scrub("value", name) == "[REDACTED]"


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


@pytest.mark.parametrize("style", ["name", "key", "Name"])
def test_name_and_value_entries_are_read_as_pairs(style: str) -> None:
    """HAR headers and Kubernetes env entries: {"name": "Authorization", "value": ...}."""
    value_key = "Value" if style == "Name" else "value"
    headers = [
        {style: "Authorization", value_key: "Basic " + NAMED_CANARY},
        {style: "Accept", value_key: "text/plain"},
    ]
    line = _json_line(lambda log: log.info("event", extra={"request": {"headers": headers}}))
    assert NAMED_CANARY not in line
    written = json.loads(line)["request"]["headers"]
    assert written == [
        {style: "Authorization", value_key: "[REDACTED]"},
        {style: "Accept", value_key: "text/plain"},
    ]
    assert without_secrets(headers)[0][value_key] == "[REDACTED]"


def _basic(user: str, secret: str) -> str:
    return base64.b64encode(f"{user}:{secret}".encode()).decode()


@pytest.mark.parametrize("fmt", ["json", "text"])
def test_basic_credentials_are_redacted_in_text(fmt: str) -> None:
    credentials = _basic("canary", NAMED_CANARY)
    setup_logging(level="INFO", fmt=fmt)
    stream = io.StringIO()
    _handler().setStream(stream)
    try:
        logging.getLogger("app.trap").info(
            "upstream sent Basic %s", credentials, extra={"note": f"Basic {credentials}"}
        )
    finally:
        setup_logging()
    assert credentials not in stream.getvalue()
    assert "Basic [CREDENTIALS_REDACTED]" in stream.getvalue()


def test_basic_in_prose_is_kept() -> None:
    assert scrub("Basic information about the plan") == "Basic information about the plan"


def _database_url() -> str:
    return "postgresql://app:" + NAMED_CANARY + "@db:5432/app"


def test_passwords_in_urls_are_redacted() -> None:
    line = _json_line(
        lambda log: log.info("connecting to %s", _database_url(), extra={"target": _database_url()})
    )
    assert NAMED_CANARY not in line
    assert json.loads(line)["target"] == "postgresql://app:[REDACTED]@db:5432/app"
    assert without_secrets({"target": _database_url()}) == {
        "target": "postgresql://app:[REDACTED]@db:5432/app"
    }


def test_a_port_and_an_address_in_a_url_are_not_taken_for_a_password() -> None:
    url = "https://host.internal:8443/path?to=" + EMAIL
    assert without_secrets(url) == url


def test_the_settings_in_extra_do_not_write_the_database_password() -> None:
    """model_dump includes the computed DATABASE_URL, which carries the password."""
    from app.core.config import settings

    in_url = f":{quote(settings.POSTGRES_PASSWORD, safe='')}@"
    assert in_url in settings.DATABASE_URL, "the URL carries the password: the test is not vacuous"
    loaded = json.loads(_json_line(lambda log: log.info("settings", extra={"loaded": settings})))[
        "loaded"
    ]
    audited = without_secrets({"loaded": settings})["loaded"]
    for written in (loaded, audited):
        for name in ("DATABASE_URL", "DATABASE_URL_SYNC", "APP_DATABASE_URL"):
            assert in_url not in written[name] and ":[REDACTED]@" in written[name], name


def test_every_json_line_stays_valid_json() -> None:
    """The text redaction once ran on the serialised line and ate quotes and commas."""

    def emit(log: logging.Logger) -> None:
        log.info("event", extra={"note": "password: x", "next": 1})
        log.info("event", extra={"note": 'api_key="abc", other', "n": [1, 2]})
        _emit_everything()

    lines = _json_line(emit).splitlines()
    assert len(lines) >= 3
    records = [json.loads(line) for line in lines]
    assert records[0]["note"] == "password=[REDACTED]" and records[0]["next"] == 1


class _Opaque:
    """An object json.dumps writes through default=str."""

    def __init__(self, text: str) -> None:
        self.text = text

    def __str__(self) -> str:
        return self.text


def _non_string_extras() -> dict[str, object]:
    from pydantic import AnyUrl

    return {
        "err": RuntimeError("connect failed: " + _database_url()),
        "raw": ("password=" + NAMED_CANARY).encode(),
        "url": AnyUrl("https://user:" + NAMED_CANARY + "@host.internal/path"),
        "other": _Opaque("api_key=" + NAMED_CANARY),
    }


def test_objects_bytes_and_urls_in_extra_are_redacted() -> None:
    line = _json_line(lambda log: log.info("event", extra=_non_string_extras()))
    assert NAMED_CANARY not in line
    record = json.loads(line)
    assert record["raw"] == "password=[REDACTED]"
    assert "user:[REDACTED]@host.internal" in record["url"]


def test_objects_bytes_and_urls_in_audit_details_lose_their_url_passwords() -> None:
    details = without_secrets(_non_string_extras())
    assert NAMED_CANARY not in json.dumps({key: details[key] for key in ("err", "url")})
    assert all(isinstance(value, str) for value in details.values())


def test_numbers_and_flags_are_written_as_they_are() -> None:
    assert scrub({"n": 3, "ratio": 0.5, "ok": True, "none": None}) == {
        "n": 3,
        "ratio": 0.5,
        "ok": True,
        "none": None,
    }


def test_a_url_with_an_empty_user_is_redacted() -> None:
    """The Valkey URL of the template has no user: redis://:password@host:6379/0."""
    from app.core.config import settings

    url = "redis://:" + NAMED_CANARY + "@redis:6379/0"
    assert scrub(url) == "redis://:[REDACTED]@redis:6379/0"
    if hasattr(settings, "REDIS_URL"):
        configured = settings.model_copy(update={"REDIS_PASSWORD": NAMED_CANARY})
        assert NAMED_CANARY in configured.REDIS_URL, "the URL carries the password: not vacuous"
        assert NAMED_CANARY not in scrub(configured.REDIS_URL)
        assert NAMED_CANARY not in json.dumps(without_secrets({"url": configured.REDIS_URL}))


@pytest.mark.parametrize(
    "text",
    [
        "a" * 40_000,
        "a-" * 20_000,
        "a@" * 20_000,
        "a.a@a" * 8_000,
        "eyJ" * 13_000,
        "a://" * 10_000,
        "redis://:" + "p" * 40_000,
        "Basic " + "a" * 40_000,
        "password " * 4_000,
        "key=" * 10_000,
        "Bearer " * 5_000,
        "sk-" * 13_000,
        "-eyJ" * 10_000,
        "_eyJ" * 10_000,
        "%3DeyJ" * 7_000,
    ],
    ids=lambda text: repr(text[:12]),
)
def test_redaction_takes_linear_time_on_hostile_text(text: str) -> None:
    """Log text comes from users: a pattern with quadratic time would stall the application."""
    started = time.perf_counter()
    scrub(text)
    without_secrets(text)
    assert time.perf_counter() - started < 0.5


@pytest.mark.parametrize("scheme", ["Basic", "basic", "BASIC"])
def test_basic_credentials_are_redacted_in_any_case(scheme: str) -> None:
    credentials = _basic("canary", NAMED_CANARY)
    written = scrub(f"authorization: {scheme} {credentials}")
    assert credentials not in written


def test_addresses_are_still_redacted() -> None:
    assert scrub(f"sent to {EMAIL} and first.last+tag@mail.example.org") == (
        "sent to [EMAIL_REDACTED] and [EMAIL_REDACTED]"
    )


@pytest.mark.parametrize(
    "before", ["Bearer%20", "token%3D", "session-", "session_", "redirect_uri=x%26t%3D"]
)
def test_a_jwt_after_an_encoded_byte_or_a_separator_is_redacted(before: str) -> None:
    written = scrub(f"GET /callback?{before}{JWT} HTTP/1.1")
    assert JWT not in written and "[JWT_REDACTED]" in written


@pytest.mark.parametrize(
    "text",
    [
        "a" * 1_000_000,
        "a-" * 500_000,
        "-eyJ" * 250_000,
        "_eyJ" * 250_000,
        "%3DeyJ" * 170_000,
        "a.a@a" * 200_000,
        "x." * 500_000,
        "eyJaaaaaaaaaaa." * 70_000,
    ],
    ids=lambda text: repr(text[:6]),
)
def test_redaction_of_a_megabyte_stays_linear(text: str) -> None:
    started = time.perf_counter()
    scrub(text)
    assert time.perf_counter() - started < 2.0


def test_an_address_glued_to_a_longer_run_is_redacted() -> None:
    glued = "requestid_" + "r" * 64 + "-" + EMAIL
    long_local = "x" * 80 + "@mail.example.org"
    assert "canary.person" not in scrub(glued) and "[EMAIL_REDACTED]" in scrub(glued)
    assert "@mail.example.org" not in scrub(long_local)


def test_keys_of_any_type_are_written_as_text() -> None:
    """A bytes, UUID or tuple key made json.dumps raise, and the line was lost."""
    org = UUID("12345678-1234-5678-1234-567812345678")
    extra = {
        "entries": {b"api_key": NAMED_CANARY, org: "seen", ("a", 1): "pair", 7: "number", EMAIL: 1}
    }
    line = _json_line(lambda log: log.info("event", extra=extra))
    assert NAMED_CANARY not in line and "canary.person" not in line
    written = json.loads(line)["entries"]
    assert written == {
        "api_key": "[REDACTED]",
        str(org): "seen",
        "('a', 1)": "pair",
        "7": "number",
        "[EMAIL_REDACTED]": 1,
    }
    audited = without_secrets(extra)["entries"]
    assert (
        audited[7] == "number"
        and audited["api_key"] == "[REDACTED]"
        and audited[str(org)] == "seen"
    )
    json.dumps(audited)


def test_a_huge_name_does_not_slow_logging_down() -> None:
    name = "a_" * 500_000
    started = time.perf_counter()
    scrub({name: "value"})
    without_secrets([(name, "value")])
    assert time.perf_counter() - started < 0.5


def _jwt_part(payload: dict[str, object]) -> str:
    return _b64(json.dumps(payload, separators=(",", ":")))


@pytest.mark.parametrize("header_size", [563, 1600])
def test_a_jwt_with_a_long_header_is_redacted(header_size: int) -> None:
    """DPoP proofs carry an RSA key in the header, x5c a certificate chain."""
    header = {"alg": "RS256", "typ": "dpop+jwt", "pad": "k" * header_size}
    token = ".".join((_jwt_part(header), _jwt_part({"sub": "canary"}), _b64("signature-canary")))
    assert len(token.split(".")[0]) >= header_size
    written = scrub(f"Authorization: DPoP {token}")
    assert token not in written and "[JWT_REDACTED]" in written


def test_an_encrypted_jwt_is_redacted() -> None:
    header = _jwt_part({"alg": "dir", "enc": "A256GCM"})
    token = ".".join(
        (header, "", _b64("iv-canary-iv"), _b64("ciphertext-canary"), _b64("tag-canary"))
    )
    assert scrub(f"token={token}") == "token=[JWT_REDACTED]"


def test_an_unsigned_jwt_is_redacted() -> None:
    token = ".".join((_jwt_part({"alg": "none"}), _jwt_part({"sub": "canary"}), ""))
    assert "[JWT_REDACTED]" in scrub(f"got {token} from the client") and token not in scrub(
        f"got {token}"
    )


def test_a_jwt_glued_to_a_digit_is_redacted() -> None:
    assert scrub(f"v2{JWT}") == "v2[JWT_REDACTED]"


def test_dotted_text_that_is_not_a_jwt_stays() -> None:
    text = "see docs.example.org/guides.configuration.secrets for the version 1.2.3"
    assert scrub(text) == text


def test_a_long_name_is_judged_by_its_end_too() -> None:
    name = "x" * 300 + "_password"
    assert scrub({name: "value"}) == {name: "[REDACTED]"}
    assert without_secrets({name: "value"}) == {name: "[REDACTED]"}


@pytest.mark.parametrize("prefix", ["x.", "api.v1.auth.", "a.b.c.d.e.f."])
def test_a_jwt_after_a_dotted_prefix_is_redacted(prefix: str) -> None:
    assert scrub(f"{prefix}{JWT}") == f"{prefix}[JWT_REDACTED]"


def test_a_sentence_dot_after_a_jwt_stays() -> None:
    assert scrub(f"the token was {JWT}.") == "the token was [JWT_REDACTED]."


@pytest.mark.parametrize(
    "text",
    [
        "version 10.2.3.4 of app.core.logging",
        "files report.final.v2.pdf and archive.tar.gz",
        "host api.eu-west-1.amazonaws.com",
        "node_modules.eyJunk.x and node_modules.eyJunkyJunkyJunk.x",
        "a.b.c.d.e.f.g",
    ],
)
def test_dotted_names_are_not_taken_for_jwts(text: str) -> None:
    assert scrub(text) == text
