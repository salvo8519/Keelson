"""Sessions end when the credentials change, against a real database (Keelstone).

Access and refresh tokens carry the session version of their user (``ver``). A password
change, a password reset, a password set by an administrator, a deactivation and an explicit
sign-out from every device raise the version, so every token issued before stops working.
The requests run through the application, under row level security, so the change made by a
user's own password change is shown to work with the application login.
"""

import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_redis
from app.core.config import settings
from app.core.security import create_password_reset_token, get_password_hash
from app.core.session_cookies import REFRESH_COOKIE
from app.db.models.organization import OrganizationMember, OrgRole
from app.db.models.user import User
from app.main import app
from app.repositories import user_repo
from app.services.organization import OrganizationService
from tests.fakes import MemoryRedis
from tests.postgres import SegregatedDatabase, require_postgres, segregated_database, serving

pytestmark = pytest.mark.anyio

API = settings.API_V1_STR
TRUSTED = settings.CORS_ORIGINS[0]
PASSWORD = "old-password-1"
NEW_PASSWORD = "new-password-2"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
async def database() -> AsyncIterator[SegregatedDatabase]:
    await require_postgres("session revocation")
    async with segregated_database() as database:
        yield database


@pytest.fixture
async def client(database: SegregatedDatabase) -> AsyncIterator[AsyncClient]:
    redis = MemoryRedis()
    app.dependency_overrides[get_redis] = lambda: redis
    with serving(app, database):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    app.dependency_overrides.clear()


async def _user(database: SegregatedDatabase, email: str, **fields: Any) -> User:
    async with database.system() as db:
        user = await user_repo.create(
            db, email=email, hashed_password=get_password_hash(PASSWORD), **fields
        )
        await OrganizationService(db).create_personal_org(user.id, email)
        await db.commit()
        return user


async def _password_hash(database: SegregatedDatabase, user: User) -> str | None:
    async with database.system() as db:
        return await user_repo.get_password_hash(db, user.id)


async def _sign_in(client: AsyncClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = await client.post(
        f"{API}/auth/login", data={"username": email, "password": password}
    )
    assert response.status_code == 200, response.text
    client.cookies.clear()  # each request below names its credentials
    return response.json()


def _bearer(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _assert_ended(client: AsyncClient, tokens: dict[str, str]) -> None:
    """The access token, the refresh token in a body and in a cookie are all refused."""
    me = await client.get(f"{API}/auth/me", headers=_bearer(tokens))
    body = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    cookie = await client.post(
        f"{API}/auth/session/refresh",
        headers={"Cookie": f"{REFRESH_COOKIE}={tokens['refresh_token']}", "Origin": TRUSTED},
    )
    assert (me.status_code, body.status_code, cookie.status_code) == (401, 401, 401)


async def test_a_password_change_ends_the_sessions_issued_before_it(client, database) -> None:
    await _user(database, "ada@example.com")
    before = await _sign_in(client, "ada@example.com")

    changed = await client.patch(
        f"{API}/users/me/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=_bearer(before),
    )

    assert changed.status_code == 204, changed.text
    await _assert_ended(client, before)
    after = await _sign_in(client, "ada@example.com", NEW_PASSWORD)
    assert (await client.get(f"{API}/auth/me", headers=_bearer(after))).status_code == 200


async def test_a_browser_keeps_its_own_session_after_changing_the_password(
    client, database
) -> None:
    await _user(database, "ada@example.com")
    login = await client.post(
        f"{API}/auth/login", data={"username": "ada@example.com", "password": PASSWORD}
    )
    cookies = {c.split("=", 1)[0]: c.split("=", 1)[1].split(";")[0] for c in login.headers.get_list("set-cookie")}
    client.cookies.clear()

    changed = await client.patch(
        f"{API}/users/me/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers={"Cookie": f"access_token={cookies['access_token']}", "Origin": TRUSTED},
    )

    assert changed.status_code == 204
    renewed = {
        c.split("=", 1)[0]: c.split("=", 1)[1].split(";")[0]
        for c in changed.headers.get_list("set-cookie")
    }
    me = await client.get(f"{API}/auth/me", headers={"Cookie": f"access_token={renewed['access_token']}"})
    assert me.status_code == 200


async def test_a_password_reset_ends_the_sessions(client, database) -> None:
    user = await _user(database, "ada@example.com")
    before = await _sign_in(client, "ada@example.com")
    token = create_password_reset_token(str(user.id), current_password_hash=await _password_hash(database, user))

    reset = await client.post(
        f"{API}/auth/password-reset/confirm", json={"token": token, "new_password": NEW_PASSWORD}
    )

    assert reset.status_code == 200, reset.text
    await _assert_ended(client, before)


async def test_a_password_set_by_an_administrator_ends_the_sessions(client, database) -> None:
    user = await _user(database, "ada@example.com")
    await _user(database, "root@example.com", role="admin", is_app_admin=True)
    before = await _sign_in(client, "ada@example.com")
    admin = await _sign_in(client, "root@example.com")

    updated = await client.patch(
        f"{API}/admin/users/{user.id}", json={"password": NEW_PASSWORD}, headers=_bearer(admin)
    )

    assert updated.status_code == 200, updated.text
    await _assert_ended(client, before)


async def test_a_deactivated_account_does_not_get_its_old_sessions_back(client, database) -> None:
    user = await _user(database, "ada@example.com")
    await _user(database, "root@example.com", role="admin", is_app_admin=True)
    before = await _sign_in(client, "ada@example.com")
    admin = await _sign_in(client, "root@example.com")

    for active in (False, True):
        response = await client.patch(
            f"{API}/admin/users/{user.id}", json={"is_active": active}, headers=_bearer(admin)
        )
        assert response.status_code == 200, response.text

    await _assert_ended(client, before)


async def test_sign_out_everywhere_ends_every_session(client, database) -> None:
    await _user(database, "ada@example.com")
    laptop = await _sign_in(client, "ada@example.com")
    phone = await _sign_in(client, "ada@example.com")

    response = await client.post(f"{API}/auth/logout-all", headers=_bearer(phone))

    assert response.status_code == 204, response.text
    await _assert_ended(client, laptop)
    await _assert_ended(client, phone)


async def test_an_open_chat_notices_that_its_session_ended(client, database) -> None:
    """The WebSocket route asks before every turn (app/api/routes/v1/agent.py)."""
    from app.api.deps import session_still_current

    user = await _user(database, "ada@example.com")
    phone = await _sign_in(client, "ada@example.com")
    assert await session_still_current(user, user.token_epoch)

    await client.post(f"{API}/auth/logout-all", headers=_bearer(phone))

    assert not await session_still_current(user, user.token_epoch)


async def test_signing_in_again_does_not_end_the_other_sessions(client, database) -> None:
    await _user(database, "ada@example.com")
    first = await _sign_in(client, "ada@example.com")
    await _sign_in(client, "ada@example.com")
    assert (await client.get(f"{API}/auth/me", headers=_bearer(first))).status_code == 200


async def test_signing_out_ends_the_refresh_token_of_that_session(client, database) -> None:
    await _user(database, "ada@example.com")
    browser = await _sign_in(client, "ada@example.com")
    program = await _sign_in(client, "ada@example.com")
    cookie = {"Cookie": f"{REFRESH_COOKIE}={browser['refresh_token']}", "Origin": TRUSTED}

    signed_out = await client.post(f"{API}/auth/session/logout", headers=cookie)
    logged_out = await client.post(
        f"{API}/auth/logout", json={"refresh_token": program["refresh_token"]}
    )

    assert (signed_out.status_code, logged_out.status_code) == (204, 204)
    assert (await client.post(f"{API}/auth/session/refresh", headers=cookie)).status_code == 401
    refused = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": program["refresh_token"]}
    )
    assert refused.status_code == 401


async def _refresh(client: AsyncClient, refresh_token: str) -> Any:
    return await client.post(f"{API}/auth/refresh", json={"refresh_token": refresh_token})


async def test_signing_out_ends_the_refresh_tokens_rotated_before(client, database) -> None:
    """A refresh token stolen before a rotation dies with the session it belongs to."""
    await _user(database, "ada@example.com")
    first = await _sign_in(client, "ada@example.com")
    rotated = await _refresh(client, first["refresh_token"])
    assert rotated.status_code == 200, rotated.text
    latest = rotated.json()

    logged_out = await client.post(f"{API}/auth/logout", json={"refresh_token": latest["refresh_token"]})

    assert logged_out.status_code == 204
    for token in (first["refresh_token"], latest["refresh_token"]):
        assert (await _refresh(client, token)).status_code == 401


async def test_a_browser_sign_out_ends_the_refresh_cookies_rotated_before(client, database) -> None:
    await _user(database, "ada@example.com")
    first = await _sign_in(client, "ada@example.com")
    old = {"Cookie": f"{REFRESH_COOKIE}={first['refresh_token']}", "Origin": TRUSTED}
    renewed = await client.post(f"{API}/auth/session/refresh", headers=old)
    assert renewed.status_code == 204, renewed.text
    latest = renewed.cookies[REFRESH_COOKIE]
    client.cookies.clear()

    signed_out = await client.post(
        f"{API}/auth/session/logout",
        headers={"Cookie": f"{REFRESH_COOKIE}={latest}", "Origin": TRUSTED},
    )

    assert signed_out.status_code == 204
    assert (await client.post(f"{API}/auth/session/refresh", headers=old)).status_code == 401


async def test_a_refresh_token_presented_again_after_rotation_ends_its_session(
    client, database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reuse detection: one of the two holders of the token is not the user."""
    from app.core import revoked_tokens

    await _user(database, "ada@example.com")
    first = await _sign_in(client, "ada@example.com")
    other = await _sign_in(client, "ada@example.com")
    second = (await _refresh(client, first["refresh_token"])).json()
    later = time.time() + revoked_tokens.REUSE_GRACE.total_seconds() + 1
    monkeypatch.setattr(revoked_tokens, "clock", lambda: later)

    replayed = await _refresh(client, first["refresh_token"])

    assert replayed.status_code == 401
    assert (await _refresh(client, second["refresh_token"])).status_code == 401
    assert (await _refresh(client, other["refresh_token"])).status_code == 200


async def test_tabs_renewing_the_same_session_at_once_both_keep_it(client, database) -> None:
    """Within the grace window a rotated token is renewed again (tabs share the cookie)."""
    await _user(database, "ada@example.com")
    first = await _sign_in(client, "ada@example.com")

    tab_a = await _refresh(client, first["refresh_token"])
    tab_b = await _refresh(client, first["refresh_token"])

    assert (tab_a.status_code, tab_b.status_code) == (200, 200)
    for tab in (tab_a, tab_b):
        assert (await _refresh(client, tab.json()["refresh_token"])).status_code == 200


async def test_a_refresh_token_without_a_session_id_is_refused(client, database) -> None:
    """Refresh tokens issued before sessions had an id cannot be ended with their session."""
    import jwt

    user = await _user(database, "ada@example.com")
    tokens = await _sign_in(client, "ada@example.com")
    claims = jwt.decode(tokens["refresh_token"], settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    del claims["sid"]
    legacy = jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert claims["sub"] == str(user.id)

    assert (await _refresh(client, legacy)).status_code == 401


async def test_a_reused_refresh_token_ends_the_browser_session_too(
    client, database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reuse detection through the refresh cookie (the path a stolen cookie takes)."""
    from app.core import revoked_tokens

    await _user(database, "ada@example.com")
    first = await _sign_in(client, "ada@example.com")
    stolen = {"Cookie": f"{REFRESH_COOKIE}={first['refresh_token']}", "Origin": TRUSTED}
    renewed = await client.post(f"{API}/auth/session/refresh", headers=stolen)
    assert renewed.status_code == 204, renewed.text
    latest = renewed.cookies[REFRESH_COOKIE]
    client.cookies.clear()
    later = time.time() + revoked_tokens.REUSE_GRACE.total_seconds() + 1
    monkeypatch.setattr(revoked_tokens, "clock", lambda: later)

    assert (await client.post(f"{API}/auth/session/refresh", headers=stolen)).status_code == 401
    current = {"Cookie": f"{REFRESH_COOKIE}={latest}", "Origin": TRUSTED}
    assert (await client.post(f"{API}/auth/session/refresh", headers=current)).status_code == 401


# --- Impersonation ends with the administrator's rights or sessions -----------------------


IMPERSONATED = "ada@example.com"


async def _open_chat_still_current(database: SegregatedDatabase, token: dict[str, str]) -> bool:
    """What the WebSocket route asks before every turn of a chat opened with ``token``."""
    from app.api.deps import session_still_current
    from app.core.security import ACCESS, read_session_token

    claims = read_session_token(token["access_token"], ACCESS)
    assert claims is not None and claims.version is not None
    async with database.system() as db:
        target = await user_repo.get_by_email(db, IMPERSONATED)
    assert target is not None
    return await session_still_current(target, claims.version, claims)


async def _impersonation(client: AsyncClient, database: SegregatedDatabase) -> tuple[User, dict[str, str]]:
    target = await _user(database, IMPERSONATED)
    root = await _user(database, "root@example.com", role="admin", is_app_admin=True)
    admin = await _sign_in(client, "root@example.com")
    issued = await client.post(f"{API}/admin/users/{target.id}/impersonate", headers=_bearer(admin))
    assert issued.status_code == 200, issued.text
    token = {"access_token": issued.json()["access_token"]}
    assert (await client.get(f"{API}/auth/me", headers=_bearer(token))).status_code == 200
    assert await _open_chat_still_current(database, token)
    return root, token


async def _impersonation_refused(client: AsyncClient, database: SegregatedDatabase, token: dict[str, str]) -> None:
    """Refused by the API, by a new WebSocket handshake and before the next turn of an open chat."""
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import patch

    from fastapi import WebSocketException

    from app.api import deps

    assert (await client.get(f"{API}/auth/me", headers=_bearer(token))).status_code == 401
    socket = SimpleNamespace(
        headers={"sec-websocket-protocol": f"access_token.{token['access_token']}"},
        state=SimpleNamespace(),
    )
    system = deps.system_session

    @asynccontextmanager
    async def db_context() -> AsyncIterator[Any]:
        async with system("test: websocket") as session:
            yield session

    with patch.object(deps, "get_db_context", db_context), pytest.raises(WebSocketException) as refused:
        await deps.get_current_user_ws(socket, None)  # type: ignore[arg-type]
    assert refused.value.code == 4001
    assert not await _open_chat_still_current(database, token)


@pytest.mark.parametrize(
    "demotion", [{"role": "user", "is_app_admin": False}, {"is_app_admin": False}, {"is_active": False}]
)
async def test_an_impersonation_ends_when_the_administrator_loses_the_role(
    client, database, demotion: dict[str, Any]
) -> None:
    root, token = await _impersonation(client, database)

    async with database.system() as db:
        await user_repo.update(db, db_user=await user_repo.get_by_id(db, root.id), update_data=demotion)
        await db.commit()

    await _impersonation_refused(client, database, token)


async def test_an_impersonation_ends_when_the_administrator_signs_out_everywhere(client, database) -> None:
    _, token = await _impersonation(client, database)
    admin = await _sign_in(client, "root@example.com")

    assert (await client.post(f"{API}/auth/logout-all", headers=_bearer(admin))).status_code == 204

    await _impersonation_refused(client, database, token)


# --- Avatars: visible to the members of a shared organization -----------------------------


@pytest.fixture
def media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "MEDIA_DIR", str(tmp_path))
    return tmp_path


async def test_an_avatar_is_served_to_the_members_of_a_shared_organization(
    client, database, media
) -> None:
    ada = await _user(database, "ada@example.com")
    bob = await _user(database, "bob@example.com")
    await _user(database, "eve@example.com")
    async with database.system() as db:
        team = await OrganizationService(db).create_personal_org(ada.id, "team@example.com")
        db.add(OrganizationMember(organization_id=team.id, user_id=bob.id, role=OrgRole.MEMBER.value))
        await db.commit()
    ada_tokens = await _sign_in(client, "ada@example.com")
    uploaded = await client.post(
        f"{API}/users/me/avatar",
        files={"file": ("me.png", PNG, "image/png")},
        headers=_bearer(ada_tokens),
    )
    assert uploaded.status_code == 200, uploaded.text
    url = f"{API}/users/avatar/{ada.id}"

    own = await client.get(url, headers=_bearer(ada_tokens))
    member = await client.get(url, headers=_bearer(await _sign_in(client, "bob@example.com")))
    stranger = await client.get(url, headers=_bearer(await _sign_in(client, "eve@example.com")))
    anonymous = await client.get(url)

    assert (own.status_code, member.status_code) == (200, 200)
    assert member.content == PNG
    assert member.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in member.headers["content-security-policy"]
    assert (stranger.status_code, anonymous.status_code) == (404, 401)
