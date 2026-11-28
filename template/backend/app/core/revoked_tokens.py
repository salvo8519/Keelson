"""Refresh tokens: rotation, reuse detection and sign-out (Keelstone).

A sign-in starts a session; every refresh token of the session carries its id (``sid``) and an
id of its own (``jti``). A refresh exchanges the presented token for a new one in the same
session and records the presented one as rotated. Signing out ends the session: every refresh
token it rotated through is refused, so a token stolen before a rotation dies with the session.

A rotated token presented again means that two parties hold it, the user and someone else, so
the session ends (reuse detection, RFC 9700, section 4.14.2). Tabs of one browser share the
refresh cookie and may renew at the same moment: a rotated token is accepted again for
``REUSE_GRACE`` after its rotation, in the same session. A thief inside that window obtains a
token of the session too, which the user's sign-out still ends.

Ending every session of a user is done by raising the user's session version instead
(``app/core/security.py``), which needs no list. Access tokens are not listed: they are
short-lived (``MAX_DEPLOYED_ACCESS_TOKEN_MINUTES``) and browsers lose their cookie when
signing out.

Every decision is taken from Redis alone, so that replicas of the API cannot disagree: the first
exchange of a token is recorded with an atomic ``SET NX`` (two exchanges at the same moment
cannot both be the first), and the grace window is measured with the clock of Redis
(``TIME``), not with the clock of the replica that answers.

The lifetime of a token is set by the clock of the replica that issued it (``exp``), which may
differ from the clock of Redis. A token whose ``exp`` is past by the clock of Redis is refused,
and every key outlives the token it guards by ``MAX_CLOCK_SKEW``, so a replica whose clock is
behind cannot accept a token after its keys have expired.

When Redis cannot answer, a refresh and a sign-out fail with ``StoreUnavailableError`` (503,
``SESSION_STORE_UNAVAILABLE``): a session that may have been ended is never renewed, and a
sign-out is not reported as recorded when it was not.
"""

import logging
from collections.abc import Awaitable
from datetime import timedelta
from typing import Protocol, TypeVar

from app.core.config import settings
from app.core.exceptions import StoreUnavailableError
from app.core.security import SessionClaims

logger = logging.getLogger(__name__)
T = TypeVar("T")

KEY_PREFIX = "auth:revoked:"
SESSION_PREFIX = "auth:revoked-session:"
ROTATED_PREFIX = "auth:rotated:"
REUSE_GRACE = timedelta(seconds=10)
# How far the clock of a replica may be from the clock of Redis: added to every key's lifetime.
MAX_CLOCK_SKEW = timedelta(minutes=5)


class TokenStore(Protocol):
    async def set(self, key: str, value: str, ttl: int | None = None, *, only_if_absent: bool = False) -> bool: ...

    async def get(self, key: str) -> str | None: ...

    async def exists(self, key: str) -> bool: ...

    async def time(self) -> float: ...


async def ask_store(answer: Awaitable[T]) -> T:
    """One call to the session store (Redis); an error of the store becomes a 503
    (``SESSION_STORE_UNAVAILABLE``), not an unhandled 500. Every route that keeps sign-in state
    in Redis (refresh tokens here, the one-time codes of single sign-on) calls it through this."""
    try:
        return await answer
    except Exception as exc:
        logger.exception("session_store_unavailable")
        raise StoreUnavailableError(
            message="Sessions cannot be renewed or ended right now. Try again in a few minutes.",
            code="SESSION_STORE_UNAVAILABLE",
            details={"reason": "session_store_unavailable"},
        ) from exc


def _session_lifetime() -> int:
    """Every token of a session was issued before now, so it expires within one lifetime."""
    return settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60 + _skew()


def _skew() -> int:
    return int(MAX_CLOCK_SKEW.total_seconds())


def _key_lifetime(claims: SessionClaims, now: float) -> int:
    """Seconds a key about ``claims`` is kept: until the token expires, plus the clock skew."""
    return max(claims.expires_at - int(now), 0) + _skew()


async def revoke(store: TokenStore, claims: SessionClaims) -> None:
    """End the session of a refresh token: the token and every other one of its session."""
    if claims.session_id:
        await ask_store(store.set(SESSION_PREFIX + claims.session_id, "1", ttl=_session_lifetime()))
    if claims.token_id:
        now = await ask_store(store.time())
        await ask_store(store.set(KEY_PREFIX + claims.token_id, "1", ttl=_key_lifetime(claims, now)))


async def is_revoked(store: TokenStore, claims: SessionClaims) -> bool:
    """The session of this refresh token was ended, or the token expired by the clock of Redis
    (a token without ids cannot be checked)."""
    if not claims.token_id or not claims.session_id:
        return True
    if claims.expires_at <= await ask_store(store.time()):
        return True
    return await ask_store(store.exists(SESSION_PREFIX + claims.session_id)) or await ask_store(
        store.exists(KEY_PREFIX + claims.token_id)
    )


async def rotate(store: TokenStore, claims: SessionClaims) -> bool:
    """Record the exchange of a refresh token; False when it is a reuse (the session ended).

    The first exchange of a token records the time of Redis, only if no exchange was recorded
    (``SET NX``); any other exchange compares the recorded time with the time of Redis: within
    ``REUSE_GRACE`` it is a concurrent renewal and is accepted, later it ends the session.
    """
    if not claims.token_id or not claims.session_id:
        return False
    now = await ask_store(store.time())
    key = ROTATED_PREFIX + claims.token_id
    if await ask_store(store.set(key, repr(now), ttl=_key_lifetime(claims, now), only_if_absent=True)):
        return True
    rotated_at = await ask_store(store.get(key))
    if rotated_at is not None and now - float(rotated_at) <= REUSE_GRACE.total_seconds():
        return True
    await revoke(store, claims)
    return False
