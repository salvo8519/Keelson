"""Error responses as Problem Details for HTTP APIs, RFC 9457 (Keelson).

Every error the application raises is returned as ``application/problem+json``:

    {
      "type": "about:blank",
      "title": "Not Found",              # HTTP reason phrase, translated
      "status": 404,
      "detail": "Organization not found", # the message, translated
      "code": "NOT_FOUND",               # stable, for programs
      "details": {...},                   # optional context
      "request_id": "..."                 # same as the X-Request-ID header
    }

Request validation errors (422) keep FastAPI's format, which clients already parse.
"""

from typing import Any

from fastapi.responses import JSONResponse

from app.core.i18n import current_language, gettext, status_title

PROBLEM_CONTENT_TYPE = "application/problem+json"


def problem_response(
    *,
    status: int,
    code: str,
    detail: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": status_title(status),
        "status": status,
        "detail": gettext(detail),
        "code": code,
    }
    if details:
        body["details"] = details
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(
        status_code=status,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers={"Content-Language": current_language(), **(headers or {})},
    )
