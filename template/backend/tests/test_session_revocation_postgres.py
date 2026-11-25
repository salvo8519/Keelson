"""Sessions end when the credentials change, against a real database (Keelson).

Access and refresh tokens carry the session version of their user (``ver``). A password
change, a password reset, a password set by an administrator, a deactivation and an explicit
sign-out from every device raise the version, so every token issued before stops working.
The requests run through the application, under row level security, so the change made by a
user's own password change is shown to work with the application login.
"""

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
from tests.postgres import SegregatedDatabase, require_postgres, segregated_database, serving

pytestmark = pytest.mark.anyio

API = settings.API_V1_STR
TRUSTED = settings.CORS_ORIGINS[0]
PASSWORD = "old-password-1"
NEW_PASSWORD = "new-password-2"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class FakeRedis:
    """The few Redis operations the sign-in routes use, in memory."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        self.values[key] = value

    async def exists(self, key: str) -> bool:
        return key in self.values

    async def get(self, key: str) -> str | None:
        return self.values.get(key)


@pytest.fixture
async def database() -> AsyncIterator[SegregatedDatabase]:
    await require_postgres("session revocation")
    async with segregated_database() as database:
        yield database


@pytest.fixture
async def client(database: SegregatedDatabase) -> AsyncIterator[AsyncClient]:
    redis = FakeRedis()
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
    token = create_password_reset_token(str(user.id), current_password_hash=user.hashed_password)

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
