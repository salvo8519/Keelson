"""Refresh tokens ended by signing out (Keelstone).

Signing out ends one session: the id (``jti``) of its refresh token is kept in Redis until the
token would have expired, and a refresh with it is refused. Ending every session of a user is
done by raising the user's session version instead (``app/core/security.py``), which needs no
list. The access token of the session is not listed: it is short-lived
(``MAX_DEPLOYED_ACCESS_TOKEN_MINUTES``) and browsers lose its cookie when signing out.

When Redis cannot answer, a refresh fails (the error propagates): a session that may have
been ended is never renewed.
"""

import time
from typing import Protocol

from app.core.security import SessionClaims

KEY_PREFIX = "auth:revoked:"


class TokenStore(Protocol):
    async def set(self, key: str, value: str, ttl: int | None = None) -> None: ...

    async def exists(self, key: str) -> bool: ...


async def revoke(store: TokenStore, claims: SessionClaims) -> None:
    """End the session of a refresh token, for the rest of its lifetime."""
    remaining = claims.expires_at - int(time.time())
    if claims.token_id and remaining > 0:
        await store.set(KEY_PREFIX + claims.token_id, "1", ttl=remaining)


async def is_revoked(store: TokenStore, claims: SessionClaims) -> bool:
    """The session of this refresh token was ended (a token without an id cannot be checked)."""
    if not claims.token_id:
        return True
    return await store.exists(KEY_PREFIX + claims.token_id)
