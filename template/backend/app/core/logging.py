"""Logging: PII redaction (upstream) and structured JSON records (Keelstone).

Every record carries the request id and, when a trace is active, the OpenTelemetry trace and
span ids, so a log line leads to its trace and to the ``request_id`` of a Problem Details
error.
"""

import json
import logging
import re
import sys
from collections.abc import Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, ClassVar

from opentelemetry import trace

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


class PiiRedactionFilter(logging.Filter):
    """Logging filter that redacts personally identifiable information.

    Automatically scrubs email addresses, JWT tokens, API keys, bearer tokens,
    and password-like values from log messages to prevent PII leaks to
    log aggregators (Datadog, CloudWatch, Logfire, etc.).

    Usage:
        logging.getLogger().addFilter(PiiRedactionFilter())
    """

    PATTERNS: ClassVar[list[tuple[re.Pattern[str], str]]] = [
        (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[EMAIL_REDACTED]"),
        # JWT tokens (header.payload.signature)
        (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"), "[JWT_REDACTED]"),
        # Keelstone API keys: the prefix identifies the key and stays, the secret goes.
        (re.compile(r"(key_[A-Za-z0-9_-]{12})\.[A-Za-z0-9_-]{20,}"), r"\1.[REDACTED]"),
        (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "[API_KEY_REDACTED]"),
        (re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}"), "[API_KEY_REDACTED]"),
        # Generic long hex/base64 secrets (40+ chars, likely tokens)
        (re.compile(r"(?:token|key|secret|password|authorization)[=: ]+['\"]?([A-Za-z0-9_/+=.-]{40,})", re.IGNORECASE), "[SECRET_REDACTED]"),
        (re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{10,}"), "Bearer [TOKEN_REDACTED]"),
        # Password/secret in key=value or key: value patterns
        (
            re.compile(
                r"(password|passwd|pwd|secret_key|api_key|apikey|auth_token|access_token|refresh_token)"
                r"[\s]*[=:]\s*['\"]?\S+['\"]?",
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


# Keelstone: fields passed with ``extra=`` whose name says they hold a secret are never written.
# Matched on the whole name or its last part (``refresh_token``), so ``input_tokens`` stays.
SENSITIVE_FIELD = re.compile(
    r"(^|_)(password|passwd|secret|token|api_?key|authori[sz]ation|cookies?|credentials?"
    r"|private_?key|hashed_password)$",
    re.IGNORECASE,
)


def _walk(value: Any, name: str, text: Callable[[str], str]) -> Any:
    if name and SENSITIVE_FIELD.search(name):
        return "[REDACTED]"
    if isinstance(value, str):
        return text(value)
    if isinstance(value, dict):
        return {k: _walk(v, str(k), text) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_walk(v, "", text) for v in value]
    return value


def scrub(value: Any, name: str = "") -> Any:
    """``extra=`` values as they may be written: secrets by name dropped, text redacted."""
    return _walk(value, name, PiiRedactionFilter._redact)


def without_secrets(value: Any) -> Any:
    """Values of fields named like secrets dropped, the rest kept (audit details)."""
    return _walk(value, "", lambda text: text)


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

    Keelstone: the whole line is redacted once more, so the text format, whose exception text
    is added by the formatter, gets the same protection as JSON.
    """

    def format(self, record: logging.LogRecord) -> str:
        return PiiRedactionFilter._redact(super().format(record))


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
