"""Logging: PII redaction (upstream) and structured JSON records (Keelstone).

Every record carries the request id and, when a trace is active, the OpenTelemetry trace and
span ids, so a log line leads to its trace and to the ``request_id`` of a Problem Details
error.
"""

import dataclasses
import json
import logging
import re
import sys
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, ClassVar

from opentelemetry import trace
from pydantic import BaseModel

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
# Keelstone: the platform administrator acting through an impersonation token, named in every
# record and audit entry of the request (``act`` claim, app/core/security.py).
acting_admin_var: ContextVar[str | None] = ContextVar("acting_admin_id", default=None)

# Loggers that install their own handlers; their records go through the root handler instead.
_SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")
# Attributes every LogRecord has; anything else was passed with ``extra=`` and is kept.
_RECORD_FIELDS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}
# Extra fields that only make sense in a terminal (uvicorn's ANSI-coloured copy of the message).
_TERMINAL_FIELDS = frozenset({"color_message"})


# Keelstone: user information of a URL, "scheme://user:" kept, the password replaced; the user
# may be empty ("redis://:password@host"). A password in a URL has its "/" percent-encoded, so
# "host:8080/path?to=a@b" is not taken for one. Limits, accepted: a scheme longer than 32
# characters or a user longer than 256 is not recognised, and a password with an unencoded
# quote (' or ") is redacted only up to the quote.
#
# The patterns below bound what they may repeat, and those that could start at every character
# of a long run start only where the run starts (a lookbehind), so that a long run of "a" or
# "a-" in a log text costs linear time instead of quadratic time (tests/test_log_trap.py
# measures it).
URL_CREDENTIALS = re.compile(
    r"((?<![a-zA-Z0-9+.-])[a-zA-Z][a-zA-Z0-9+.-]{0,31}://[^:/@\s\"']{0,256}:)[^\s\"'/]+@"
)


# Keelstone: JWTs in two steps, so that the time stays linear on any text. JWT_RUN finds runs of
# three or more dot-separated base64url parts; the lookbehind on the whole class, dot included,
# gives each run a single start, and the quantifiers are possessive. _redact_jwt then looks for
# the part that carries a JWT header ("eyJ", base64 of '{"', in a part of 13 characters or
# more, followed by at least two parts): at its start, after "_", "-" or a digit
# ("session-eyJ...", "20eyJ..." of "Bearer%20eyJ..."), or, for the first part, after the two
# hexadecimal digits of a percent-encoded byte ("%3DeyJ..."). It redacts from the header to the
# end of the run, keeping what precedes ("x.", "api.v1.") and a sentence's final dot. A header
# glued to letters ("tokeneyJ...") is not recognised (accepted).
JWT_RUN = re.compile(r"(?<![A-Za-z0-9_.-])[A-Za-z0-9_-]++(?:\.[A-Za-z0-9_-]*+){2,}+")
_JWT_HEADER_START = re.compile(r"(?:^|[_0-9-])eyJ")
_JWT_MIN_HEADER = 13
_PERCENT_ESCAPE_DIGITS = re.compile(r"[0-9A-Fa-f]{2}")


def _jwt_header_offset(part: str, *, after_escape: bool) -> int | None:
    """Where the JWT header starts in a part, or None."""
    if after_escape and _PERCENT_ESCAPE_DIGITS.fullmatch(part[:2]) and part[2:5] == "eyJ":
        return 2
    found = _JWT_HEADER_START.search(part)
    if found is None or len(part) - (found.end() - 3) < _JWT_MIN_HEADER:
        return None
    return found.end() - 3


def _redact_jwt(match: re.Match[str]) -> str:
    run = match.group()
    parts = run.split(".")
    after_escape = match.start() > 0 and match.string[match.start() - 1] == "%"
    consumed = 0
    for index, part in enumerate(parts[:-2]):
        offset = _jwt_header_offset(part, after_escape=after_escape and index == 0)
        if offset is not None:
            token_parts = len(parts) - index
            # "header.payload.signature." at the end of a sentence: the dot stays outside. An
            # unsigned token ("header.payload.") keeps its empty last part.
            tail = "." if parts[-1] == "" and token_parts >= 4 else ""
            return run[: consumed + offset] + "[JWT_REDACTED]" + tail
        consumed += len(part) + 1
    return run


class PiiRedactionFilter(logging.Filter):
    """Logging filter that redacts personally identifiable information.

    Automatically scrubs email addresses, JWT tokens, API keys, bearer tokens,
    and password-like values from log messages to prevent PII leaks to
    log aggregators (Datadog, CloudWatch, Logfire, etc.).

    Usage:
        logging.getLogger().addFilter(PiiRedactionFilter())
    """

    PATTERNS: ClassVar[list[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]]] = [
        # Keelstone: the password of a URL ("postgresql://user:password@host/db"), before the
        # e-mail pattern, which would otherwise take "password@host.example" for an address.
        (URL_CREDENTIALS, r"\1[REDACTED]@"),
        # Keelstone: bounded as RFC 5321 bounds an address (64 and 253 characters), possessive so
        # a start does not backtrack: upstream's unbounded form took seconds on 40 KB of "a". A
        # local part glued to a longer run ("requestid_..._john.doe@example.com") is redacted
        # from its last 64 characters; a domain over 253 characters is redacted up to a label
        # within them (accepted: such a domain is not valid).
        (
            re.compile(r"[a-zA-Z0-9._%+-]{1,64}+@[a-zA-Z0-9.-]{1,253}\.[a-zA-Z]{2,63}"),
            "[EMAIL_REDACTED]",
        ),
        # JWT tokens: signed (three parts), unsigned (an empty last part) and encrypted (JWE,
        # five parts). Keelstone: see _redact_jwt; no bound on the header (DPoP proofs and x5c
        # chains carry kilobytes).
        (JWT_RUN, _redact_jwt),
        # Keelstone API keys: the prefix identifies the key and stays, the secret goes.
        (re.compile(r"(key_[A-Za-z0-9_-]{12})\.[A-Za-z0-9_-]{20,}"), r"\1.[REDACTED]"),
        (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "[API_KEY_REDACTED]"),
        (re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}"), "[API_KEY_REDACTED]"),
        # Generic long hex/base64 secrets (40+ chars, likely tokens)
        (
            re.compile(
                r"(?:token|key|secret|password|authorization)[=: ]+['\"]?([A-Za-z0-9_/+=.-]{40,})",
                re.IGNORECASE,
            ),
            "[SECRET_REDACTED]",
        ),
        (re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{10,}"), "Bearer [TOKEN_REDACTED]"),
        # Keelstone: HTTP Basic credentials (base64 of "user:password"). The value must carry an
        # upper case letter after its first character, a digit or "+/=", so prose such as
        # "Basic information" stays.
        (
            re.compile(r"\b(?i:basic)\s+(?=.[A-Za-z0-9+/]*[A-Z0-9+/=])[A-Za-z0-9+/]{8,}={0,2}"),
            "Basic [CREDENTIALS_REDACTED]",
        ),
        # Password/secret in key=value or key: value patterns
        (
            re.compile(
                r"(password|passwd|pwd|secret_key|api_key|apikey|auth_token|access_token|refresh_token)"
                # Keelstone: the value stops at a quote or a comma, so the redaction of a line
                # never removes the punctuation around it.
                r"[\s]*[=:]\s*['\"]?[^\s'\",]+['\"]?",
                re.IGNORECASE,
            ),
            r"\1=[REDACTED]",
        ),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact PII from the formatted message.

        Keelstone: upstream redacted the template and the arguments separately. A template such
        as ``"password=%s"`` lost its ``%s`` to the redaction, formatting then failed, and
        logging printed the raw arguments, the password included, to standard error. The
        message is now formatted first and redacted as a whole.
        """
        record.msg = self._redact(record.getMessage())
        record.args = None
        return True

    @classmethod
    def _redact(cls, value: str) -> str:
        for pattern, replacement in cls.PATTERNS:
            value = pattern.sub(replacement, value)
        return value


# Keelstone: fields passed with ``extra=`` (and audit details) whose name says they hold a secret
# are never written. A name is split into words at "_", "-", ".", spaces and camelCase
# ("newPassword", "X-API-Key", "S3_SECRET_KEY" all give their words); digits ending a word and
# version words are dropped ("accessToken2", "api_key_v2" are "access token", "api key").
#
# These mark a secret when a word contains them ("password_confirm", "PGPASSWORD",
# "webhooksecret", "credentials_json"), except the flags and paths of CREDENTIAL_SETTINGS:
SECRET_FRAGMENTS = ("password", "passwd", "passphrase", "passcode", "secret", "credential")
# "allow_credentials" and "with_credentials" are flags, "credentials_file" a path.
CREDENTIAL_FLAG_WORDS = frozenset({"allow", "with"})
CREDENTIAL_PATH_WORDS = frozenset({"file", "path"})
# These when a word is exactly one of them ("pwd", "otp_code", "totp_seed", "aws_creds"):
SECRET_WORDS = frozenset({"pwd", "pwds", "otp", "otps", "totp", "creds", "dsn", "dsns"})
# Whole names of a session identifier, which is a bearer credential ("session_id", "sessionId");
# "checkout_session_id" or "session_count" stay visible.
SESSION_ID_NAMES = (("session", "id"), ("sessionid",))
# These as the last word or before a word of SECRET_CARRIER_WORDS ("Authorization",
# "authorization_header", "Set-Cookie", "mfa", "xsrf"): "cookie_name" and "authorization_url"
# stay visible.
SECRET_LAST_WORDS = frozenset(
    {"authorization", "authorisation", "cookie", "cookies", "mfa", "csrf", "xsrf"}
)
SECRET_CARRIER_WORDS = frozenset({"header", "headers", "value", "values", "code", "codes"})
# "code" or "codes" after one of these is a one-time code ("recovery_codes", "mfa_code").
ONE_TIME_CODE_WORDS = frozenset(
    {
        "auth",
        "authorization",
        "authorisation",
        "backup",
        "mfa",
        "oauth",
        "otp",
        "recovery",
        "reset",
        "totp",
        "verification",
    }
)
# A token or a key, in any position and in the plural: "refresh_tokens", "private_key_pem",
# "apiKeyHash", "encryption_key_v1", and their fused forms ("accesstoken", "apikeys", "sshkey",
# "tokenhash", "refreshtokenhash").
# "verifier" and "assertion" are the PKCE code verifier and the signed client assertion of OAuth.
TOKEN_WORDS = frozenset({"token", "key", "jwt", "bearer", "verifier", "assertion"})
# These are a secret even alone; a bare "key" is not (see _is_secret_token).
BARE_SECRET_TOKEN_WORDS = frozenset({"token", "jwt", "bearer", "verifier", "assertion"})
FUSED_TOKEN_WORDS = frozenset(
    {
        "accesstoken",
        "apitoken",
        "authtoken",
        "bearertoken",
        "csrftoken",
        "idtoken",
        "refreshtoken",
        "sessiontoken",
        "xsrftoken",
        "accesskey",
        "apikey",
        "encryptionkey",
        "masterkey",
        "privatekey",
        "secretkey",
        "signingkey",
        "sshkey",
    }
)
_TOKEN_ROOTS = TOKEN_WORDS | FUSED_TOKEN_WORDS
# A token or key word followed by one of these names something about the secret, not the
# secret ("token_type", "key_id", "api_key_prefix", "token_url", "ACCESS_TOKEN_EXPIRE_MINUTES").
HARMLESS_NEXT_WORDS = frozenset(
    {
        "algorithm",
        "audience",
        "count",
        "endpoint",
        "expiration",
        "expire",
        "expires",
        "expiry",
        "format",
        "header",
        "id",
        "ids",
        "issuer",
        "kind",
        "length",
        "lifetime",
        "limit",
        "limits",
        "name",
        "names",
        "prefix",
        "scope",
        "scopes",
        "size",
        "status",
        "ttl",
        "type",
        "types",
        "uri",
        "url",
        "usage",
        "version",
    }
)
# A token word after one of these counts language model tokens ("input_tokens", "max_tokens").
COUNTING_WORDS = frozenset(
    {
        "cached",
        "completion",
        "input",
        "max",
        "min",
        "num",
        "output",
        "prompt",
        "reasoning",
        "remaining",
        "total",
        "used",
    }
)
_WORD_BOUNDARY = re.compile(r"[^0-9a-zA-Z]+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_VERSION_WORD = re.compile(r"^v?[0-9]+$")


def _words(name: str) -> list[str]:
    words = []
    for word in _WORD_BOUNDARY.split(name):
        if not word or _VERSION_WORD.match(word.lower()):
            continue
        if stripped := word.lower().rstrip("0123456789"):
            words.append(stripped)
    return words


def _singular(word: str) -> str:
    return word[:-1] if word.endswith("s") and word[:-1] in _TOKEN_ROOTS else word


def _at(words: list[str], index: int) -> str | None:
    return words[index] if 0 <= index < len(words) else None


def _is_secret_fragment(words: list[str], index: int) -> bool:
    word = words[index]
    if not any(fragment in word for fragment in SECRET_FRAGMENTS):
        return False
    is_flag = _at(words, index - 1) in CREDENTIAL_FLAG_WORDS
    is_path = _at(words, index + 1) in CREDENTIAL_PATH_WORDS
    return not (word.startswith("credential") and (is_flag or is_path))


def _is_secret_token(words: list[str], index: int) -> bool:
    word = _singular(words[index])
    if word.endswith("hash") and _singular(word.removesuffix("hash")) in _TOKEN_ROOTS:
        return True  # "tokenhash", "keyhash", "refreshtokenhash"
    if word not in _TOKEN_ROOTS:
        return False
    following = _at(words, index + 1)
    if following in HARMLESS_NEXT_WORDS:
        return False
    if word in FUSED_TOKEN_WORDS:
        return True
    if index == 0:
        # A bare "key" is the public prefix of an API key or the name of an e-mail template, and a
        # leading "tokens" or "keys" counts something ("tokens_used"); "token" or "jwt" alone, or
        # "key_pem", is a secret.
        return words[0] == word and (word in BARE_SECRET_TOKEN_WORDS or following is not None)
    return words[index - 1] not in COUNTING_WORDS


def _is_secret_carrier(words: list[str], index: int) -> bool:
    word = words[index]
    following = _at(words, index + 1)
    if word in SECRET_LAST_WORDS and (following is None or following in SECRET_CARRIER_WORDS):
        return True
    return word in ("code", "codes") and _at(words, index - 1) in ONE_TIME_CODE_WORDS


def is_secret_name(name: str) -> bool:
    """True for a field name that says the field holds a secret.

    Deliberately broad: a field is hidden when in doubt. Names hidden although they are not
    secrets, accepted: ``object_key``, ``idempotency_key``, ``cache_key``, ``primary_key``,
    ``public_key``, ``sort_key``, ``page_token``, ``next_token``, ``otp_enabled``,
    ``totp_enabled`` and any word containing "secret" ("secretary"). Names kept visible: ``key``,
    ``keys``, ``tokens``, ``key_id``, ``token_type``, ``api_key_prefix``, ``input_tokens``,
    ``max_tokens``, ``cookie_name``, ``mfa_enabled``, ``ACCESS_TOKEN_EXPIRE_MINUTES``,
    ``CORS_ALLOW_CREDENTIALS``, ``checkout_session_id``, ``client_assertion_type``, ``monkey``,
    ``keyword``.
    """
    words = _words(name)
    if tuple(words) in SESSION_ID_NAMES:
        return True
    return any(
        word in SECRET_WORDS
        or _is_secret_fragment(words, index)
        or _is_secret_carrier(words, index)
        or _is_secret_token(words, index)
        for index, word in enumerate(words)
    )


def _plain(value: Any) -> Any:
    """Models, dataclasses and mappings as dictionaries, so their fields are checked by name."""
    if isinstance(value, BaseModel):
        return value.model_dump()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        # Shallow, unlike dataclasses.asdict, which deep-copies every value: nested values are
        # walked in turn.
        return {field.name: getattr(value, field.name) for field in dataclasses.fields(value)}
    if isinstance(value, Mapping) and not isinstance(value, dict):
        return dict(value)
    return value


def _name_of(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("latin-1")
    return None


def _value_name(entry: dict[Any, Any]) -> str | None:
    """The name of a {"name": ..., "value": ...} entry (HAR headers, Kubernetes env, tags)."""
    keys = {str(key).lower(): key for key in entry}
    if "value" not in keys:
        return None
    label = next((entry[keys[key]] for key in ("name", "key") if key in keys), None)
    return _name_of(label)


# Values JSON writes as they are; any other object is written as its text, redacted like text.
_JSON_SCALARS = (int, float, bool, type(None))


# A name longer than this is judged by its beginning and its end: a huge name must not slow
# logging down, and "<long prefix>_password" is still a secret.
_MAX_NAME_LENGTH = 256


def _is_secret_long_name(name: str) -> bool:
    if len(name) <= _MAX_NAME_LENGTH:
        return is_secret_name(name)
    return is_secret_name(name[:_MAX_NAME_LENGTH]) or is_secret_name(name[-_MAX_NAME_LENGTH:])


def _key(key: Any, text: Callable[[str], str]) -> Any:
    """A dictionary key JSON can write: numbers and flags kept, anything else as redacted text."""
    if isinstance(key, _JSON_SCALARS):
        return key
    return text(_name_of(key) or str(key))


def _walk(value: Any, name: str, text: Callable[[str], str]) -> Any:
    if name and _is_secret_long_name(name):
        return "[REDACTED]"
    value = _plain(value)
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return text(value)
    if isinstance(value, dict):
        entry_name = _value_name(value)
        return {
            _key(k, text): _walk(
                v,
                entry_name
                if entry_name is not None and str(k).lower() == "value"
                else (_name_of(k) or str(k)),
                text,
            )
            for k, v in value.items()
        }
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and (pair_name := _name_of(value[0])) is not None
    ):
        # A name and its value, as headers travel: [("Authorization", "Basic ...")].
        return [_walk(value[0], "", text), _walk(value[1], pair_name, text)]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_walk(v, "", text) for v in value]
    if isinstance(value, _JSON_SCALARS):
        return value
    # Exceptions, URLs (pydantic AnyUrl, httpx.URL), identifiers, dates and any other object:
    # json.dumps(default=str) would print their text unredacted.
    return text(str(value))


def scrub(value: Any, name: str = "") -> Any:
    """``extra=`` values as they may be written: secrets by name dropped, text redacted."""
    return _walk(value, name, PiiRedactionFilter._redact)


def without_secrets(value: Any) -> Any:
    """Values of fields named like secrets dropped, passwords in URLs too, the rest kept (audit
    details)."""
    return _walk(value, "", lambda text: URL_CREDENTIALS.sub(r"\1[REDACTED]@", text))


class ContextFilter(logging.Filter):
    """Adds the request id and the current trace and span ids to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.acting_admin_id = acting_admin_var.get()
        context = trace.get_current_span().get_span_context()
        record.trace_id = format(context.trace_id, "032x") if context.is_valid else None
        record.span_id = format(context.span_id, "016x") if context.is_valid else None
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, ready for Loki, Elasticsearch or CloudWatch."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _RECORD_FIELDS and key not in _TERMINAL_FIELDS and value is not None:
                # Keelstone: upstream redacted the message only; extra fields went out as given.
                entry[key] = scrub(value, key)
        if record.exc_info:
            # Exceptions carry SQL parameters, request data and URLs: redacted like messages.
            entry["exception"] = PiiRedactionFilter._redact(self.formatException(record.exc_info))
        return json.dumps(entry, default=str, ensure_ascii=False)


class _AppHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """The application's handler, recognised when logging is configured again.

    Keelstone: a text line is redacted once more, so the exception text the formatter adds gets
    the same protection as JSON. A JSON line is not: JsonFormatter redacts each value already,
    and a pattern applied to the serialised line could break its quoting.
    """

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        return (
            line if isinstance(self.formatter, JsonFormatter) else PiiRedactionFilter._redact(line)
        )


TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"


def setup_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Configure the root logger: one handler, PII redaction, request and trace context.

    Idempotent, so tests and the lifespan can call it again.
    """
    handler = _AppHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else logging.Formatter(TEXT_FORMAT))
    # Filters on a handler run for records propagated from every logger. Upstream attached the
    # redaction filter to the root logger, where it only saw records logged on the root itself.
    handler.addFilter(PiiRedactionFilter())
    handler.addFilter(ContextFilter())

    root_logger = logging.getLogger()
    # Replace only a previous handler of ours: test runners and tools keep theirs.
    root_logger.handlers = [h for h in root_logger.handlers if not isinstance(h, _AppHandler)]
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
    for name in _SERVER_LOGGERS:
        server_logger = logging.getLogger(name)
        server_logger.handlers = []
        server_logger.propagate = True
