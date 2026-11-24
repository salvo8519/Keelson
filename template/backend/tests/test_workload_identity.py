"""Workload identity: CI jobs authenticate with their own OpenID Connect token (Keelson)."""

import time
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient

from app.core import workload_identity as wi
from app.core.config import settings

ISSUER = wi.GITHUB_ACTIONS_ISSUER
AUDIENCE = "https://api.example.com"
ORG = uuid4()
TRUST = wi.WorkloadTrust(
    name="deploy-main",
    issuer=ISSUER,
    audience=AUDIENCE,
    claims={"repository": "acme/service", "ref": "refs/heads/main"},
    organization_id=ORG,
    scopes=["agent:run"],
)
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _ci_token(key=KEY, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "repo:acme/service:ref:refs/heads/main",
        "repository": "acme/service",
        "ref": "refs/heads/main",
        "iat": now,
        "exp": now + 300,
        **overrides,
    }
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> None:
    """The issuer's published key is KEY (no network)."""
    signing = SimpleNamespace(key=KEY.public_key())
    client = SimpleNamespace(get_signing_key_from_jwt=lambda _token: signing)

    async def _client(_issuer: str):
        return client

    monkeypatch.setattr(wi, "_jwks_client", _client)


@pytest.mark.anyio
async def test_a_token_of_the_trusted_repository_and_branch_is_accepted(github) -> None:
    trust, claims = await wi.verify(_ci_token(), [TRUST])
    assert trust is TRUST and claims["repository"] == "acme/service"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "overrides",
    [
        {"repository": "acme/other"},
        {"ref": "refs/heads/feature"},
        {"aud": "https://elsewhere.example.com"},
        {"exp": int(time.time()) - 10},
        {"iss": "https://gitlab.com"},
    ],
)
async def test_other_repositories_branches_audiences_and_issuers_are_refused(
    github, overrides: dict
) -> None:
    with pytest.raises(wi.WorkloadRefused):
        await wi.verify(_ci_token(**overrides), [TRUST])


@pytest.mark.anyio
async def test_a_token_signed_by_another_key_is_refused(github) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(wi.WorkloadRefused):
        await wi.verify(_ci_token(key=other), [TRUST])


def test_a_trust_must_constrain_the_token() -> None:
    base = TRUST.model_dump()
    for change in ({"claims": {}}, {"issuer": "http://ci.example.com"}, {"scopes": ["root"]}):
        with pytest.raises(ValueError):
            wi.WorkloadTrust(**{**base, **change})


def test_the_credential_carries_the_organization_and_scopes_until_it_expires() -> None:
    credential, expires_at = wi.issue(TRUST, settings.SECRET_KEY)
    read = wi.read(credential, settings.SECRET_KEY)
    assert read is not None
    assert (read.organization_id, read.scopes, read.expires_at) == (
        ORG,
        frozenset({"agent:run"}),
        expires_at,
    )
    expired, _ = wi.issue(TRUST, settings.SECRET_KEY, now=time.time() - 7200)
    assert wi.read(expired, settings.SECRET_KEY) is None
    assert wi.read(credential, "another-secret-key-of-at-least-32-chars") is None


def test_a_user_access_token_is_not_a_workload_credential() -> None:
    from app.core.security import create_access_token

    assert wi.read(wi.CREDENTIAL_PREFIX + create_access_token("user-id"), settings.SECRET_KEY) is None


@pytest.mark.anyio
async def test_a_workload_credential_acts_like_an_api_key(client: AsyncClient) -> None:
    credential, _ = wi.issue(TRUST, settings.SECRET_KEY)
    response = await client.get("/api/v1/api-keys/introspect", headers={"X-API-Key": credential})
    assert response.status_code == 200
    body = response.json()
    assert (body["organization_id"], body["scopes"]) == (str(ORG), ["agent:run"])


@pytest.mark.anyio
async def test_the_exchange_issues_a_credential_only_for_a_trusted_token(
    client: AsyncClient, github, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "WORKLOAD_IDENTITIES", [TRUST])
    url = "/api/v1/auth/workload-token"

    refused = await client.post(url, json={"token": _ci_token(repository="acme/other")})
    accepted = await client.post(url, json={"token": _ci_token()})

    assert refused.status_code == 401
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["credential"].startswith(wi.CREDENTIAL_PREFIX)
    assert (body["organization_id"], body["scopes"]) == (str(ORG), ["agent:run"])
