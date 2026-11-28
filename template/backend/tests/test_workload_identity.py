"""Workload identity: CI jobs authenticate with their own OpenID Connect token (Keelstone)."""

import time
import uuid
from types import SimpleNamespace
from uuid import uuid4

import httpx
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


def _ci_token(key=KEY, drop: tuple[str, ...] = (), **overrides) -> str:
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
    for claim in drop:
        del claims[claim]
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """The issuer's published key is KEY (no network). Records (issuer, token) of each lookup."""
    signing = SimpleNamespace(key=KEY.public_key())
    lookups: list[tuple[str, str]] = []

    async def _client(issuer: str):
        def _signing_key(token: str):
            lookups.append((issuer, token))
            return signing

        return SimpleNamespace(get_signing_key_from_jwt=_signing_key)

    monkeypatch.setattr(wi, "_jwks_client", _client)
    return lookups


@pytest.mark.anyio
async def test_a_token_of_the_trusted_repository_and_branch_is_accepted(github) -> None:
    token = _ci_token()
    trust, claims = await wi.verify(token, [TRUST])
    assert trust is TRUST and claims["repository"] == "acme/service"
    # The key is looked up at the token's own issuer, for this very token.
    assert github == [(ISSUER, token)]


@pytest.mark.anyio
async def test_a_token_with_several_audiences_is_accepted_when_one_is_ours(github) -> None:
    trust, _ = await wi.verify(_ci_token(aud=["https://other.example.com", AUDIENCE]), [TRUST])
    assert trust is TRUST


@pytest.mark.anyio
async def test_every_trust_is_tried_before_refusing(github) -> None:
    other_audience = TRUST.model_copy(update={"name": "staging", "audience": "https://staging.example.com"})
    other_repository = TRUST.model_copy(update={"name": "other", "claims": {"repository": "acme/other"}})
    trust, _ = await wi.verify(_ci_token(), [other_audience, other_repository, TRUST])
    assert trust is TRUST


@pytest.mark.anyio
async def test_an_issuer_written_with_a_trailing_slash_is_the_trusted_issuer(github) -> None:
    token = _ci_token(iss=ISSUER + "/")
    trust, claims = await wi.verify(token, [TRUST])
    assert trust is TRUST and claims["iss"] == ISSUER
    assert github == [(ISSUER, token)]


@pytest.mark.anyio
@pytest.mark.parametrize("claim", ["exp", "iat", "aud"])
async def test_a_token_without_a_required_claim_is_refused(github, claim: str) -> None:
    with pytest.raises(wi.WorkloadRefused, match="verification failed"):
        await wi.verify(_ci_token(drop=(claim,)), [TRUST])


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("token", "reason"),
    [
        ("not-a-jwt", "not a JWT"),
        (_ci_token(iss="https://ci.example.com"), "the issuer is not trusted"),
        (_ci_token(drop=("iss",)), "the issuer is not trusted"),
        (_ci_token(repository="acme/other"), "no trust matches"),
    ],
)
async def test_a_refusal_says_why_for_the_log(github, token: str, reason: str) -> None:
    with pytest.raises(wi.WorkloadRefused, match=reason):
        await wi.verify(token, [TRUST])


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
    read = wi.read(credential, settings.SECRET_KEY, [TRUST])
    assert read is not None
    assert (read.trust, read.organization_id, read.scopes, read.expires_at) == (
        "deploy-main",
        ORG,
        frozenset({"agent:run"}),
        expires_at,
    )
    expired, _ = wi.issue(TRUST, settings.SECRET_KEY, now=time.time() - 7200)
    assert wi.read(expired, settings.SECRET_KEY, [TRUST]) is None
    assert wi.read(credential, "another-secret-key-of-at-least-32-chars", [TRUST]) is None


def test_the_credential_records_when_it_was_issued() -> None:
    now = time.time()
    credential, expires_at = wi.issue(TRUST, settings.SECRET_KEY, now=now)
    payload = jwt.decode(credential[len(wi.CREDENTIAL_PREFIX) :], settings.SECRET_KEY, algorithms=["HS256"])
    assert (payload["iat"], payload["exp"], payload["sub"]) == (int(now), int(now) + 900, "workload:deploy-main")
    assert expires_at.timestamp() == int(now) + 900


def _payload() -> dict:
    """The claims of a credential of TRUST, as issue writes them."""
    return {
        "type": wi.TOKEN_TYPE,
        "sub": "workload:deploy-main",
        "org": str(ORG),
        "scopes": ["agent:run"],
        "trust": wi.trust_digest(TRUST),
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }


def test_a_credential_built_like_issue_is_read() -> None:
    """The baseline of the test below: the payload alone is a valid credential."""
    credential = wi.CREDENTIAL_PREFIX + jwt.encode(_payload(), settings.SECRET_KEY, algorithm="HS256")
    assert wi.read(credential, settings.SECRET_KEY, [TRUST]) is not None


@pytest.mark.parametrize("claim", ["exp", "iat", "sub", "org", "scopes", "type", "trust"])
def test_a_credential_without_a_required_claim_is_refused(claim: str) -> None:
    """In particular, a credential that never expires is never accepted."""
    payload = _payload()
    del payload[claim]
    credential = wi.CREDENTIAL_PREFIX + jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    assert wi.read(credential, settings.SECRET_KEY, [TRUST]) is None


def test_a_credential_follows_its_trust_as_configured_now() -> None:
    """Removing a trust, moving it or narrowing its scopes applies to credentials already issued."""
    credential, _ = wi.issue(TRUST.model_copy(update={"scopes": ["agent:run", "knowledge:read"]}), settings.SECRET_KEY)
    assert wi.read(credential, settings.SECRET_KEY, []) is None, "trust removed"
    moved = TRUST.model_copy(update={"organization_id": uuid.uuid4()})
    assert wi.read(credential, settings.SECRET_KEY, [moved]) is None, "trust moved to another organization"
    narrowed = wi.read(credential, settings.SECRET_KEY, [TRUST])
    assert narrowed is not None and narrowed.scopes == frozenset({"agent:run"})
    renamed = TRUST.model_copy(update={"name": "deploy-other"})
    assert wi.read(credential, settings.SECRET_KEY, [renamed]) is None


@pytest.mark.parametrize(
    "change",
    [
        {"issuer": "https://gitlab.com"},
        {"audience": "https://other.example.com"},
        {"claims": {"repository": "acme/service", "ref": "refs/heads/feature"}},
        {"claims": {"repository": "acme/service"}},
        {"claims": {"repository": "acme/service", "ref": "refs/heads/main", "environment": "prod"}},
    ],
)
def test_a_credential_stops_when_its_trust_accepts_other_tokens(change: dict) -> None:
    """A trust whose issuer, audience or claims changed no longer vouches for its credentials."""
    credential, _ = wi.issue(TRUST, settings.SECRET_KEY)
    assert wi.read(credential, settings.SECRET_KEY, [TRUST.model_copy(update=change)]) is None
    assert wi.read(credential, settings.SECRET_KEY, [TRUST]) is not None, "unchanged trust"


def test_a_credential_stops_when_its_trust_gets_a_shorter_lifetime() -> None:
    """Credentials issued for longer than the trust allows now stop; shorter ones go on."""
    credential, _ = wi.issue(TRUST.model_copy(update={"ttl_seconds": 3600}), settings.SECRET_KEY)
    assert wi.read(credential, settings.SECRET_KEY, [TRUST.model_copy(update={"ttl_seconds": 3600})]) is not None
    assert wi.read(credential, settings.SECRET_KEY, [TRUST.model_copy(update={"ttl_seconds": 900})]) is None
    short, _ = wi.issue(TRUST.model_copy(update={"ttl_seconds": 300}), settings.SECRET_KEY)
    assert wi.read(short, settings.SECRET_KEY, [TRUST.model_copy(update={"ttl_seconds": 900})]) is not None


def test_the_trust_digest_does_not_depend_on_the_order_of_the_claims() -> None:
    reordered = TRUST.model_copy(update={"claims": dict(reversed(list(TRUST.claims.items())))})
    assert wi.trust_digest(reordered) == wi.trust_digest(TRUST)


# --- Discovery of the issuer's keys ---------------------------------------------------------


@pytest.fixture
def discovery(monkeypatch: pytest.MonkeyPatch) -> dict:
    """The issuer's metadata is served by a mock transport; records requests and timeouts."""
    seen: dict = {"urls": [], "timeouts": [], "metadata": {"issuer": ISSUER, "jwks_uri": ISSUER + "/jwks"}}
    real_client = httpx.AsyncClient

    def _handler(request: httpx.Request) -> httpx.Response:
        seen["urls"].append(str(request.url))
        return httpx.Response(200, json=seen["metadata"])

    def _client(**kwargs):
        seen["timeouts"].append(kwargs.get("timeout"))
        return real_client(transport=httpx.MockTransport(_handler), **kwargs)

    monkeypatch.setattr(wi.httpx, "AsyncClient", _client)
    monkeypatch.setattr(wi, "_jwks_clients", {})
    return seen


@pytest.mark.anyio
async def test_the_keys_are_read_from_the_issuers_published_metadata(discovery: dict) -> None:
    client = await wi._jwks_client(ISSUER)
    assert isinstance(client, jwt.PyJWKClient) and client.uri == ISSUER + "/jwks"
    assert discovery["urls"] == [ISSUER + "/.well-known/openid-configuration"]
    assert discovery["timeouts"] == [wi.DISCOVERY_TIMEOUT_SECONDS]
    # Read once per issuer.
    assert await wi._jwks_client(ISSUER) is client
    assert len(discovery["urls"]) == 1


@pytest.mark.anyio
async def test_metadata_that_names_another_issuer_is_refused(discovery: dict) -> None:
    discovery["metadata"] = {"issuer": "https://attacker.example.com", "jwks_uri": "https://attacker.example.com/k"}
    with pytest.raises(wi.WorkloadRefused, match="another issuer"):
        await wi._jwks_client(ISSUER)
    assert wi._jwks_clients == {}


@pytest.mark.anyio
async def test_metadata_without_an_issuer_is_refused(discovery: dict) -> None:
    discovery["metadata"] = {"jwks_uri": ISSUER + "/jwks"}
    with pytest.raises(wi.WorkloadRefused):
        await wi._jwks_client(ISSUER)


@pytest.mark.anyio
async def test_metadata_may_write_the_issuer_with_a_trailing_slash(discovery: dict) -> None:
    discovery["metadata"] = {"issuer": ISSUER + "/", "jwks_uri": ISSUER + "/jwks"}
    assert (await wi._jwks_client(ISSUER)).uri == ISSUER + "/jwks"


def test_a_user_access_token_is_not_a_workload_credential() -> None:
    from app.core.security import create_access_token

    assert wi.read(wi.CREDENTIAL_PREFIX + create_access_token("user-id", version=0), settings.SECRET_KEY, [TRUST]) is None


@pytest.mark.anyio
async def test_a_workload_credential_acts_like_an_api_key(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WORKLOAD_IDENTITIES", [TRUST])
    credential, _ = wi.issue(TRUST, settings.SECRET_KEY)
    response = await client.get("/api/v1/api-keys/introspect", headers={"X-API-Key": credential})
    assert response.status_code == 200
    body = response.json()
    assert (body["organization_id"], body["scopes"]) == (str(ORG), ["agent:run"])
    # The trust is removed from the settings: the credential already issued stops at once.
    monkeypatch.setattr(settings, "WORKLOAD_IDENTITIES", [])
    response = await client.get("/api/v1/api-keys/introspect", headers={"X-API-Key": credential})
    assert response.status_code == 401


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
