"""Logging: PII redaction (upstream) and structured JSON records (Keelson).

Every record carries the request id and, when a trace is active, the OpenTelemetry trace and
span ids, so a log line leads to its trace and to the ``request_id`` of a Problem Details
error.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, ClassVar

from opentelemetry import trace

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Loggers that install their own handlers; their records go through the root handler instead.
_SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")
# Attributes every LogRecord has; anything else was passed with ``extra=`` and is kept.
_RECORD_FIELDS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


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
        """Redact PII from log record message and args."""
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._redact(v) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self._redact(a) if isinstance(a, str) else a for a in record.args)
        return True

    def _redact(self, value: str) -> str:
        for pattern, replacement in self.PATTERNS:
            value = pattern.sub(replacement, value)
        return value


class ContextFilter(logging.Filter):
    """Adds the request id and the current trace and span ids to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
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
            if key not in _RECORD_FIELDS and value is not None:
                entry[key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


class _AppHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """The application's handler, recognised when logging is configured again."""


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
