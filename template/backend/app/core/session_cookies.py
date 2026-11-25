"""The browser session in HttpOnly cookies (Keelstone).

Upstream's React frontend kept the access and refresh tokens in localStorage, where any script
running in the page, an injected one included, can read and send them elsewhere. Browsers now
receive the tokens as cookies that scripts cannot read:

* ``access_token``: HttpOnly, sent with every API request; it lives as long as the token.
* ``refresh_token``: HttpOnly, sent only to ``/api/v1/auth/session``, where a new pair is
  issued; never readable by the page and never in a response body.

Both are ``SameSite=Lax`` and, outside local development, ``Secure``. Cookies travel with
requests a browser makes on its own, so requests authenticated by a cookie are also checked
against cross-site request forgery: an unsafe method (or a WebSocket handshake) must come from
an origin listed in ``CORS_ORIGINS``.

Programs (scripts, other services, CI) keep using ``Authorization: Bearer`` or API keys, which
browsers never attach by themselves and which need no such check.
"""

from urllib.parse import urlsplit

from fastapi import Request, Response

from app.core.config import settings
from app.core.exceptions import AuthorizationError

ACCESS_COOKIE = "access_token"  # noqa: S105 - a cookie name, not a secret
REFRESH_COOKIE = "refresh_token"  # noqa: S105 - a cookie name, not a secret
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LOCAL_ENVIRONMENTS = frozenset({"local", "development"})


def refresh_path() -> str:
    return f"{settings.API_V1_STR}/auth/session"


def secure_cookies() -> bool:
    """Secure outside local development, where the API is served over plain HTTP."""
    return settings.ENVIRONMENT not in LOCAL_ENVIRONMENTS


def set_session_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=secure_cookies(),
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=secure_cookies(),
        samesite="lax",
        path=refresh_path(),
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/", secure=secure_cookies(), httponly=True)
    response.delete_cookie(
        REFRESH_COOKIE, path=refresh_path(), secure=secure_cookies(), httponly=True
    )


def _origin(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def trusted_origin(origin: str | None, referer: str | None = None) -> bool:
    """The request comes from one of the frontends allowed by CORS_ORIGINS.

    A present Origin header decides alone, "null" (an opaque origin: a sandboxed frame, a
    redirect across sites) and an empty value included; the Referer is read only when the
    browser sent no Origin, never as a second chance for a refused one.
    """
    allowed = {_origin(entry) for entry in settings.CORS_ORIGINS} - {None}
    source = origin if origin is not None else referer
    return _origin(source) in allowed


def require_trusted_origin(request: Request) -> None:
    """Refuse a cookie-authenticated unsafe request from another site (CSRF)."""
    if request.method in SAFE_METHODS:
        return
    if not trusted_origin(request.headers.get("origin"), request.headers.get("referer")):
        raise AuthorizationError(message="Request origin not allowed")


def refuse_foreign_origin(request: Request) -> None:
    """Refuse a request that names another site in Origin or Referer (login CSRF).

    Signing in and out sets or removes cookies without a session to check, so a form on
    another site could sign the browser into the attacker's account. Browsers name the site
    of a form; programs send neither header and are accepted.
    """
    origin, referer = request.headers.get("origin"), request.headers.get("referer")
    if (origin is not None or referer is not None) and not trusted_origin(origin, referer):
        raise AuthorizationError(message="Request origin not allowed")
