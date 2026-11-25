"""Session security without a database (Keelstone): versions, CSRF, limits, impersonation.

The database side (the version raised by a password change, under row level security) is in
``tests/test_session_revocation_postgres.py``.
"""

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
    assert claims["act"] == {"sub": str(admin.id)}


async def test_actions_and_logs_under_impersonation_name_the_administrator(
    client: AsyncClient, users, user, caplog: pytest.LogCaptureFixture
) -> None:
    from app.core.audit import record_audit
    from app.core.logging import ContextFilter
    from app.core.security import create_access_token

    admin_id = uuid4()
    token = create_access_token(str(user.id), version=user.token_epoch, actor=admin_id)
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
