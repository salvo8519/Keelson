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

When Redis cannot answer, a refresh fails (the error propagates): a session that may have
been ended is never renewed.
"""

import time
from datetime import timedelta
from typing import Protocol

from app.core.config import settings
from app.core.security import SessionClaims

KEY_PREFIX = "auth:revoked:"
SESSION_PREFIX = "auth:revoked-session:"
ROTATED_PREFIX = "auth:rotated:"
REUSE_GRACE = timedelta(seconds=10)

# The clock of the grace window (replaced in tests).
clock = time.time


class TokenStore(Protocol):
    async def set(self, key: str, value: str, ttl: int | None = None) -> None: ...

    async def get(self, key: str) -> str | None: ...

    async def exists(self, key: str) -> bool: ...


def _session_lifetime() -> int:
    """Every token of a session was issued before now, so it expires within one lifetime."""
    return settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60


async def revoke(store: TokenStore, claims: SessionClaims) -> None:
    """End the session of a refresh token: the token and every other one of its session."""
    if claims.session_id:
        await store.set(SESSION_PREFIX + claims.session_id, "1", ttl=_session_lifetime())
    remaining = claims.expires_at - int(clock())
    if claims.token_id and remaining > 0:
        await store.set(KEY_PREFIX + claims.token_id, "1", ttl=remaining)


async def is_revoked(store: TokenStore, claims: SessionClaims) -> bool:
    """The session of this refresh token was ended (a token without ids cannot be checked)."""
    if not claims.token_id or not claims.session_id:
        return True
    return await store.exists(SESSION_PREFIX + claims.session_id) or await store.exists(
        KEY_PREFIX + claims.token_id
    )


async def rotate(store: TokenStore, claims: SessionClaims) -> bool:
    """Record the exchange of a refresh token; False when it is a reuse (the session ended).

    The first exchange of a token is recorded; a second one within ``REUSE_GRACE`` is a
    concurrent renewal and is accepted; a later one ends the session.
    """
    if not claims.token_id or not claims.session_id:
        return False
    now = clock()
    key = ROTATED_PREFIX + claims.token_id
    rotated_at = await store.get(key)
    if rotated_at is None:
        await store.set(key, str(now), ttl=max(claims.expires_at - int(now), 1))
        return True
    if now - float(rotated_at) <= REUSE_GRACE.total_seconds():
        return True
    await revoke(store, claims)
    return False
