"""Session security without a database (Keelstone): versions, CSRF, limits, impersonation.

The database side (the version raised by a password change, under row level security) is in
``tests/test_session_revocation_postgres.py``.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import jwt
import pytest
from fastapi import WebSocketException
from httpx import AsyncClient

from app.api import deps
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.session_cookies import ACCESS_COOKIE, REFRESH_COOKIE
from app.main import app
from app.services.rate_limit import DEFAULT_RATE_LIMITS, RateLimitCategory
from tests.fakes import FailingRedis
from tests.overrides import override_user_service

pytestmark = pytest.mark.anyio

API = settings.API_V1_STR
TRUSTED = settings.CORS_ORIGINS[0]
EVIL = "https://evil.example"


def _user(**fields: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "email": "ada@example.com",
        "full_name": "Ada",
        "is_active": True,
        "role": "user",
        "is_app_admin": False,
        "locale": None,
        "token_epoch": 0,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "avatar_url": None,
    }
    values.update(fields)
    return SimpleNamespace(**values)


@pytest.fixture
def user() -> SimpleNamespace:
    return _user()


@pytest.fixture
def users(user: SimpleNamespace) -> AsyncIterator[MagicMock]:
    service = MagicMock()
    service.authenticate = AsyncMock(return_value=user)
    service.get_by_id = AsyncMock(return_value=user)
    override_user_service(app, service)
    yield service
    app.dependency_overrides.clear()


async def _sign_in(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        f"{API}/auth/login", data={"username": "ada@example.com", "password": "pw-123456"}
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- Session version -----------------------------------------------------------------------


async def test_tokens_carry_the_session_version(client: AsyncClient, users, user) -> None:
    user.token_epoch = 7
    tokens = await _sign_in(client)
    for token in tokens["access_token"], tokens["refresh_token"]:
        assert jwt.decode(token, options={"verify_signature": False})["ver"] == 7


async def test_tokens_of_an_older_version_are_refused(client: AsyncClient, users, user) -> None:
    tokens = await _sign_in(client)
    user.token_epoch += 1  # what a password change does

    bearer = await client.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    cookie = await client.get(
        f"{API}/auth/me", headers={"Cookie": f"{ACCESS_COOKIE}={tokens['access_token']}"}
    )
    body = await client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    session = await client.post(
        f"{API}/auth/session/refresh",
        headers={"Cookie": f"{REFRESH_COOKIE}={tokens['refresh_token']}", "Origin": TRUSTED},
    )

    assert [r.status_code for r in (bearer, cookie, body, session)] == [401, 401, 401, 401]


async def test_the_token_of_a_deleted_user_is_unauthorized_not_missing(
    client: AsyncClient, users
) -> None:
    tokens = await _sign_in(client)
    users.get_by_id = AsyncMock(side_effect=NotFoundError(message="User not found"))
    me = await client.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    refreshed = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert (me.status_code, refreshed.status_code) == (401, 401)


async def test_a_websocket_refuses_a_token_of_an_older_version(
    client: AsyncClient, users, user
) -> None:
    tokens = await _sign_in(client)
    user.token_epoch += 1
    socket = SimpleNamespace(
        headers={"sec-websocket-protocol": f"access_token.{tokens['access_token']}"},
        state=SimpleNamespace(),
    )

    @asynccontextmanager
    async def db_context() -> AsyncIterator[MagicMock]:
        yield MagicMock(refresh=AsyncMock())

    with (
        patch.object(deps, "get_db_context", db_context),
        patch.object(deps, "UserService", return_value=users),
        pytest.raises(WebSocketException) as refused,
    ):
        await deps.get_current_user_ws(socket, None)  # type: ignore[arg-type]
    assert refused.value.code == 4001


# --- Login CSRF ----------------------------------------------------------------------------


@pytest.mark.parametrize("header", ["Origin", "Referer"])
async def test_a_cross_site_login_sets_no_cookie(client: AsyncClient, users, header: str) -> None:
    response = await client.post(
        f"{API}/auth/login",
        data={"username": "ada@example.com", "password": "pw-123456"},
        headers={header: EVIL + ("/" if header == "Referer" else "")},
    )
    assert response.status_code == 403
    assert response.headers.get_list("set-cookie") == []
    users.authenticate.assert_not_awaited()


async def test_a_login_from_the_frontend_or_a_program_is_accepted(
    client: AsyncClient, users
) -> None:
    form = {"username": "ada@example.com", "password": "pw-123456"}
    trusted = await client.post(f"{API}/auth/login", data=form, headers={"Origin": TRUSTED})
    program = await client.post(f"{API}/auth/login", data=form)
    assert (trusted.status_code, program.status_code) == (200, 200)


async def test_a_cross_site_sign_out_is_refused(client: AsyncClient) -> None:
    response = await client.post(f"{API}/auth/session/logout", headers={"Origin": EVIL})
    assert response.status_code == 403
    assert response.headers.get_list("set-cookie") == []


# --- Rate limits of the session refresh ----------------------------------------------------


async def test_failed_logins_do_not_block_the_refresh_of_other_sessions(
    client: AsyncClient, users
) -> None:
    tokens = await _sign_in(client)
    for _ in range(DEFAULT_RATE_LIMITS[RateLimitCategory.AUTH].per_ip or 0):
        await client.post(f"{API}/auth/login", data={"username": "x@example.com", "password": "x"})
    assert (await client.post(f"{API}/auth/login", data={"username": "x", "password": "x"})).status_code == 429

    renewed = await client.post(
        f"{API}/auth/session/refresh",
        headers={"Cookie": f"{REFRESH_COOKIE}={tokens['refresh_token']}", "Origin": TRUSTED},
    )
    assert renewed.status_code == 204


async def test_the_refresh_limit_is_per_user(client: AsyncClient, users, user) -> None:
    ada = (await _sign_in(client))["refresh_token"]
    bob_user = _user(email="bob@example.com")
    users.authenticate = AsyncMock(return_value=bob_user)
    bob = (await _sign_in(client))["refresh_token"]
    by_id = {user.id: user, bob_user.id: bob_user}
    users.get_by_id = AsyncMock(side_effect=lambda user_id: by_id[user_id])
    limit = DEFAULT_RATE_LIMITS[RateLimitCategory.REFRESH].per_user or 0

    statuses = [
        (await client.post(f"{API}/auth/refresh", json={"refresh_token": ada})).status_code
        for _ in range(limit + 1)
    ]
    other = await client.post(f"{API}/auth/refresh", json={"refresh_token": bob})

    assert statuses[:limit] == [200] * limit and statuses[limit] == 429
    assert other.status_code == 200


# --- Impersonation -------------------------------------------------------------------------


async def test_an_impersonation_token_names_the_administrator(client: AsyncClient, user) -> None:
    admin = _user(email="root@example.com", role="admin", is_app_admin=True)
    service = MagicMock(get_by_id=AsyncMock(return_value=user))
    db = MagicMock(execute=AsyncMock())
    checker = deps.CurrentAdmin.__metadata__[0].dependency
    app.dependency_overrides[checker] = lambda: admin
    app.dependency_overrides[deps.get_admin_db_session] = lambda: db
    app.dependency_overrides[deps.get_admin_user_service] = lambda: service
    try:
        response = await client.post(f"{API}/admin/users/{user.id}/impersonate")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    claims = jwt.decode(response.json()["access_token"], options={"verify_signature": False})
    assert claims["sub"] == str(user.id)
    assert claims["act"] == {"sub": str(admin.id), "ver": admin.token_epoch}


async def test_actions_and_logs_under_impersonation_name_the_administrator(
    client: AsyncClient, users, user, caplog: pytest.LogCaptureFixture
) -> None:
    from app.core.audit import record_audit
    from app.core.logging import ContextFilter
    from app.core.security import create_access_token

    admin = _user(email="root@example.com", role="admin", is_app_admin=True)
    admin_id = admin.id
    token = create_access_token(str(user.id), version=user.token_epoch, actor=admin)
    seen: dict[str, object] = {}

    @app.get("/_test/impersonation")
    async def probe(current: deps.CurrentUser) -> dict[str, str]:  # type: ignore[name-defined]
        db = MagicMock(execute=AsyncMock())
        await record_audit(db, actor_user_id=current.id, action="test.action")
        seen["values"] = db.execute.await_args.args[0].compile().params
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "m", None, None)
        ContextFilter().filter(record)
        seen["log"] = record.acting_admin_id
        return {}

    try:
        with patch.object(deps, "actor_still_current", AsyncMock(return_value=True)):
            response = await client.get(
                "/_test/impersonation", headers={"Authorization": f"Bearer {token}"}
            )
    finally:
        app.router.routes.pop()

    assert response.status_code == 200
    assert seen["values"]["details"] == {"acting_admin_id": str(admin_id)}  # type: ignore[index]
    assert seen["log"] == str(admin_id)


# --- Registration does not tell which addresses have an account ----------------------------


async def test_registration_answers_the_same_for_a_new_and_a_known_address(
    client: AsyncClient, users, user
) -> None:
    form = {"email": "ada@example.com", "password": "password123", "full_name": "Ada"}
    users.register = AsyncMock(return_value=user)
    new = await client.post(f"{API}/auth/register", json=form)
    users.register = AsyncMock(return_value=None)
    known = await client.post(f"{API}/auth/register", json=form)

    assert (new.status_code, known.status_code) == (202, 202)
    assert new.json() == known.json()


async def test_registering_a_known_address_tells_its_owner_and_creates_nothing() -> None:
    from app.schemas.user import UserRegister
    from app.services.user import UserService

    owner = _user(locale="it")
    email = MagicMock(send_account_exists=AsyncMock())
    with (
        patch("app.services.user.user_repo.get_by_email", new=AsyncMock(return_value=owner)),
        patch("app.services.user.user_repo.create", new=AsyncMock()) as create,
        patch("app.services.user.get_email_service", return_value=email),
    ):
        result = await UserService(MagicMock()).register(
            UserRegister(email="ada@example.com", password="password123")
        )

    assert result is None
    create.assert_not_awaited()
    email.send_account_exists.assert_awaited_once()
    assert email.send_account_exists.await_args.kwargs["language"] == "it"


# --- Refresh token rotation (app/core/revoked_tokens.py) ----------------------------------


def _refresh_claims(session_id: str | None = None):
    from app.core.security import REFRESH, create_refresh_token, read_session_token

    claims = read_session_token(create_refresh_token(uuid4(), version=0, session_id=session_id), REFRESH)
    assert claims is not None
    return claims


async def test_a_rotation_keeps_the_session_and_gives_a_new_token_id() -> None:
    first = _refresh_claims()
    rotated = _refresh_claims(first.session_id)

    assert first.session_id and rotated.session_id == first.session_id
    assert rotated.token_id != first.token_id


async def test_a_sign_in_time_is_set_at_sign_in_and_kept_by_rotations() -> None:
    from app.core.security import ACCESS, REFRESH, issue_session_tokens, read_session_token

    user = SimpleNamespace(id=uuid4(), token_epoch=0)
    access, refresh = issue_session_tokens(user)
    started = read_session_token(refresh, REFRESH)
    assert started is not None and started.signed_in_at is not None
    assert abs(started.signed_in_at - datetime.now(UTC).timestamp()) < 5

    access, rotated = issue_session_tokens(user, started.session_id, started.signed_in_at - 600)
    for token, kind in ((rotated, REFRESH), (access, ACCESS)):
        claims = read_session_token(token, kind)
        assert claims is not None and claims.signed_in_at == started.signed_in_at - 600


async def test_a_token_exchanged_again_after_the_grace_window_ends_its_session() -> None:
    from app.core import revoked_tokens
    from tests.fakes import MemoryRedis

    store = MemoryRedis()
    first = _refresh_claims()
    sibling = _refresh_claims(first.session_id)
    other_session = _refresh_claims()

    assert await revoked_tokens.rotate(store, first)
    store.now += revoked_tokens.REUSE_GRACE.total_seconds()
    assert await revoked_tokens.rotate(store, first), "a concurrent renewal within the window"
    store.now += 1
    assert not await revoked_tokens.rotate(store, first), "a reuse after the window"

    assert await revoked_tokens.is_revoked(store, sibling)
    assert not await revoked_tokens.is_revoked(store, other_session)


class InterleavingRedis:
    """A Redis whose every operation yields to the other tasks first, as network calls do, with
    a clock that answers the next value of ``times`` at every ``TIME``."""

    def __init__(self, times: list[float]) -> None:
        from tests.fakes import MemoryRedis

        self.inner = MemoryRedis()
        self.times = times

    async def set(self, key: str, value: str, ttl: int | None = None, *, only_if_absent: bool = False) -> bool:
        await asyncio.sleep(0)
        return await self.inner.set(key, value, ttl, only_if_absent=only_if_absent)

    async def get(self, key: str) -> str | None:
        await asyncio.sleep(0)
        return await self.inner.get(key)

    async def exists(self, key: str) -> bool:
        await asyncio.sleep(0)
        return await self.inner.exists(key)

    async def time(self) -> float:
        await asyncio.sleep(0)
        return self.times.pop(0)


async def test_concurrent_exchanges_record_the_first_one_only() -> None:
    """Two exchanges at once: both are renewals of one session, and the later one does not move
    the start of the grace window (a read then a write would let it, and a reuse inside the
    moved window would be accepted)."""
    from app.core import revoked_tokens

    grace = revoked_tokens.REUSE_GRACE.total_seconds()
    start = 1_000_000.0
    store = InterleavingRedis([start, start + grace - 1, start + grace + 1, start + grace + 1])
    first = _refresh_claims()
    sibling = _refresh_claims(first.session_id)

    together = await asyncio.gather(revoked_tokens.rotate(store, first), revoked_tokens.rotate(store, first))

    assert together == [True, True]
    assert await store.inner.get(revoked_tokens.ROTATED_PREFIX + str(first.token_id)) == repr(start)
    assert not await revoked_tokens.rotate(store, first), "a reuse after the window of the first exchange"
    assert await revoked_tokens.is_revoked(store.inner, sibling)


async def test_concurrent_reuses_after_the_window_both_end_the_session() -> None:
    from app.core import revoked_tokens

    grace = revoked_tokens.REUSE_GRACE.total_seconds()
    store = InterleavingRedis([0.0, grace + 1, grace + 1, grace + 1, grace + 1])
    first = _refresh_claims()
    assert await revoked_tokens.rotate(store, first)

    replayed = await asyncio.gather(revoked_tokens.rotate(store, first), revoked_tokens.rotate(store, first))

    assert replayed == [False, False]
    assert await revoked_tokens.is_revoked(store.inner, first)


async def test_the_grace_window_follows_the_clock_of_redis_not_of_the_replica(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replicas with clocks set apart agree: only the time of Redis is read."""
    import time

    from app.core import revoked_tokens
    from tests.fakes import MemoryRedis

    store = MemoryRedis()
    first = _refresh_claims()
    assert await revoked_tokens.rotate(store, first)

    monkeypatch.setattr(time, "time", lambda: store.now + 3600)
    assert await revoked_tokens.rotate(store, first), "a replica one hour ahead, within the window"
    monkeypatch.undo()
    store.now += revoked_tokens.REUSE_GRACE.total_seconds() + 1
    monkeypatch.setattr(time, "time", lambda: store.now - 3600)
    assert not await revoked_tokens.rotate(store, first), "a replica one hour behind, after the window"


async def test_a_token_expired_by_the_clock_of_redis_is_refused() -> None:
    """A replica whose clock is behind Redis still finds the token valid; Redis decides."""
    from app.core import revoked_tokens
    from tests.fakes import MemoryRedis

    store = MemoryRedis()
    claims = _refresh_claims()
    store.now = claims.expires_at - 1
    assert not await revoked_tokens.is_revoked(store, claims)

    store.now = claims.expires_at + 1

    assert await revoked_tokens.is_revoked(store, claims)


async def test_the_keys_of_a_token_outlive_it_by_the_clock_skew() -> None:
    from app.core import revoked_tokens
    from tests.fakes import MemoryRedis

    store = MemoryRedis()
    claims = _refresh_claims()
    store.now = claims.expires_at - 30
    skew = int(revoked_tokens.MAX_CLOCK_SKEW.total_seconds())

    assert await revoked_tokens.rotate(store, claims)
    await revoked_tokens.revoke(store, claims)

    assert store.ttls[revoked_tokens.ROTATED_PREFIX + str(claims.token_id)] == 30 + skew
    assert store.ttls[revoked_tokens.KEY_PREFIX + str(claims.token_id)] == 30 + skew
    assert (store.ttls[revoked_tokens.SESSION_PREFIX + str(claims.session_id)] or 0) >= (
        settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60 + skew
    )


class BrokenClockRedis(FailingRedis):
    """A Redis whose ``TIME`` fails; the other operations work."""

    def __init__(self) -> None:
        super().__init__("time")


async def test_without_the_clock_of_redis_a_refresh_fails_closed() -> None:
    """No answer from Redis: no token is renewed, and signing out still ends the session. The
    error of the store is a 503 of the application, not an unhandled exception."""
    from app.core import revoked_tokens
    from app.core.exceptions import StoreUnavailableError
    from tests.fakes import MemoryRedis

    broken = BrokenClockRedis()
    claims = _refresh_claims()
    for call in (revoked_tokens.rotate, revoked_tokens.is_revoked, revoked_tokens.revoke):
        with pytest.raises(StoreUnavailableError) as unavailable:
            await call(broken, claims)
        assert (unavailable.value.status_code, unavailable.value.code) == (503, "SESSION_STORE_UNAVAILABLE")

    healthy = MemoryRedis()
    healthy.values = broken.inner.values
    assert await revoked_tokens.is_revoked(healthy, claims), "the session was ended before the failure"


async def test_a_refresh_without_the_clock_of_redis_issues_no_token(users, user) -> None:
    from httpx import ASGITransport

    from app.core.security import issue_session_tokens

    _, refresh = issue_session_tokens(user)
    app.dependency_overrides[deps.get_redis] = BrokenClockRedis
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as ac:
            body = await ac.post(f"{API}/auth/refresh", json={"refresh_token": refresh})
            cookie = await ac.post(
                f"{API}/auth/session/refresh",
                headers={"Cookie": f"{REFRESH_COOKIE}={refresh}", "Origin": TRUSTED},
            )
    finally:
        app.dependency_overrides.pop(deps.get_redis, None)

    for response in (body, cookie):
        assert response.status_code == 503, response.text
        assert response.json()["code"] == "SESSION_STORE_UNAVAILABLE"
        assert int(response.headers["Retry-After"]) > 0
        assert "access_token" not in response.text
        assert response.headers.get_list("set-cookie") == []


async def test_a_failed_lookup_of_a_revocation_is_not_a_valid_token(users, user) -> None:
    """The clock of Redis answers but the lookup of the revocations does not: the token is not
    taken for valid (no fail open), and the refresh answers 503."""
    from httpx import ASGITransport

    from app.core import revoked_tokens
    from app.core.exceptions import StoreUnavailableError
    from app.core.security import issue_session_tokens

    with pytest.raises(StoreUnavailableError):
        await revoked_tokens.is_revoked(FailingRedis("exists"), _refresh_claims())

    _, refresh = issue_session_tokens(user)
    app.dependency_overrides[deps.get_redis] = lambda: FailingRedis("exists")
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as ac:
            response = await ac.post(f"{API}/auth/refresh", json={"refresh_token": refresh})
    finally:
        app.dependency_overrides.pop(deps.get_redis, None)

    assert response.status_code == 503, response.text
    assert response.json()["code"] == "SESSION_STORE_UNAVAILABLE"
    assert "access_token" not in response.text


async def test_signing_out_while_redis_is_down_says_the_session_was_not_ended(users, user) -> None:
    """A program learns that its sign-out was not recorded; a browser is signed out all the
    same (its cookies are removed) and learns that the refresh token was not revoked."""
    from httpx import ASGITransport

    from app.core.i18n import gettext
    from app.core.security import issue_session_tokens
    from tests.fakes import DownRedis

    _, refresh = issue_session_tokens(user)
    app.dependency_overrides[deps.get_redis] = DownRedis
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as ac:
            program = await ac.post(f"{API}/auth/logout", json={"refresh_token": refresh})
            browser = await ac.post(
                f"{API}/auth/session/logout",
                headers={"Cookie": f"{REFRESH_COOKIE}={refresh}", "Origin": TRUSTED, "Accept-Language": "it"},
            )
    finally:
        app.dependency_overrides.pop(deps.get_redis, None)

    for response in (program, browser):
        assert response.status_code == 503, response.text
        assert response.json()["code"] == "SESSION_STORE_UNAVAILABLE"
        assert int(response.headers["Retry-After"]) > 0
    for response in (program, browser):
        assert response.json()["details"]["revocation_recorded"] is False
    assert browser.json()["detail"] == gettext(
        "Sessions cannot be renewed or ended right now. Try again in a few minutes.", "it"
    )
    cleared = " ".join(browser.headers.get_list("set-cookie"))
    for cookie in (ACCESS_COOKIE, REFRESH_COOKIE):
        assert f'{cookie}=""' in cleared or f"{cookie}=;" in cleared, cleared


async def test_a_token_without_ids_counts_as_revoked() -> None:
    from dataclasses import replace

    from app.core import revoked_tokens
    from tests.fakes import MemoryRedis

    claims = _refresh_claims()
    for legacy in (replace(claims, session_id=None), replace(claims, token_id=None)):
        assert await revoked_tokens.is_revoked(MemoryRedis(), legacy)
