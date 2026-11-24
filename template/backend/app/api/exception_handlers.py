"""Exception handlers for FastAPI application.

These handlers convert domain exceptions to proper HTTP responses.
WebSocket connections that raise an ``AppException`` before ``accept()`` are
handled too — Starlette closes the socket with 403 and we just log the
incident; we cannot return an HTTP body for a non-HTTP scope.
"""

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import HTTPConnection

from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException
from app.core.i18n import N_
from app.core.problems import problem_response

# Keelson: messages of the framework's own errors, so that they are translated too.
FRAMEWORK_MESSAGES = (
    N_("Not authenticated"),
    N_("Not Found"),
    N_("Method Not Allowed"),
)

logger = logging.getLogger(__name__)


def _connection_meta(conn: HTTPConnection) -> dict[str, Any]:
    """Common log fields shared by HTTP requests and WebSocket connections.

    ``method`` exists only on HTTP ``Request`` — for WebSockets we surface the
    scope type so log filters can still distinguish the two.
    """
    return {
        "path": conn.url.path,
        "method": getattr(conn, "method", None) or conn.scope.get("type", "unknown"),
    }


def _is_websocket(conn: HTTPConnection) -> bool:
    return conn.scope.get("type") == "websocket"


async def app_exception_handler(
    request: HTTPConnection, exc: AppException
) -> JSONResponse | None:
    """Handle application exceptions for both HTTP and WebSocket scopes.

    Logs 5xx errors as errors and 4xx as warnings. Returns a JSON response
    for HTTP scopes; returns ``None`` for WebSocket scopes (Starlette will
    close the socket on its own).
    """
    log_extra = {
        "error_code": exc.code,
        "status_code": exc.status_code,
        "details": exc.details,
        **_connection_meta(request),
    }

    if exc.status_code >= 500:
        logger.error("%s: %s", exc.code, exc.message, extra=log_extra)
    else:
        logger.warning("%s: %s", exc.code, exc.message, extra=log_extra)

    if _is_websocket(request):
        return None

    headers: dict[str, str] = dict(exc.headers or {})
    if exc.status_code == 401:
        headers["WWW-Authenticate"] = "Bearer"

    # Keelson: Problem Details (RFC 9457) with a translated detail (app/core/problems.py).
    return problem_response(
        status=exc.status_code,
        code=exc.code,
        detail=exc.message,
        details=exc.details,
        request_id=getattr(request.state, "request_id", None),
        headers=headers,
    )


async def unhandled_exception_handler(
    request: HTTPConnection, exc: Exception
) -> JSONResponse | None:
    """Handle unexpected exceptions.

    Logs the full exception but returns a generic error to the client
    to avoid leaking sensitive information.
    """
    logger.exception("Unhandled exception", extra=_connection_meta(request))

    if _is_websocket(request):
        return None

    return problem_response(
        status=500,
        code="INTERNAL_ERROR",
        detail=N_("An unexpected error occurred"),
        request_id=getattr(request.state, "request_id", None),
    )


async def http_exception_handler(
    request: HTTPConnection, exc: StarletteHTTPException
) -> JSONResponse | None:
    """Keelson: errors raised by the framework (401 of the OAuth2 scheme, unknown routes)
    as Problem Details too. A non-string detail keeps the framework's response."""
    if _is_websocket(request):
        return None
    if not isinstance(exc.detail, str):
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers
        )
    return problem_response(
        status=exc.status_code,
        code=f"HTTP_{exc.status_code}",
        detail=exc.detail,
        request_id=getattr(request.state, "request_id", None),
        headers=dict(exc.headers or {}),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI app.

    Call this after creating the FastAPI application instance.
    """
    # Handler returns None for WebSocket connections (no JSONResponse there),
    # which Starlette's HTTP-handler type doesn't model.
    app.add_exception_handler(AppException, app_exception_handler)  # ty: ignore[invalid-argument-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # ty: ignore[invalid-argument-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)  # ty: ignore[invalid-argument-type]
