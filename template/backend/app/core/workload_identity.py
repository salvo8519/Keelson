"""Workload identity: CI jobs authenticate with their own OpenID Connect token (Keelstone).

GitHub Actions and GitLab CI give every job a short-lived token signed by their issuer that
names the repository, the branch and the workflow. A trust in the settings says which of
those tokens may act for which organization, with which API key scopes:

    WORKLOAD_IDENTITIES=[
      {"name": "deploy-main", "issuer": "https://token.actions.githubusercontent.com",
       "audience": "https://api.example.com",
       "claims": {"repository_id": "123456789", "ref": "refs/heads/main"},
       "organization_id": "<uuid>", "scopes": ["agent:run"], "ttl_seconds": 900}
    ]

The job exchanges its token at ``POST /api/v1/auth/workload-token`` for a credential of this
API, valid for ``ttl_seconds`` and sent like an API key (``X-API-Key: wl.<token>``). No secret
is stored in the CI: nothing to leak, rotate or revoke there.

Prefer immutable claims: ``repository_id`` (GitHub) or ``project_id`` (GitLab) rather than the
repository name, which another account can take after a rename, a transfer or a deletion.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import jwt
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app.core.api_keys import unknown_scopes

GITHUB_ACTIONS_ISSUER = "https://token.actions.githubusercontent.com"
GITLAB_ISSUER = "https://gitlab.com"
CREDENTIAL_PREFIX = "wl."
TOKEN_TYPE = "workload"  # noqa: S105 - the type claim of the credential, not a secret
SIGNING_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384"]
DISCOVERY_TIMEOUT_SECONDS = 5.0


class WorkloadTrust(BaseModel):
    """Which CI tokens may act for an organization, and with which scopes."""

    name: str = Field(pattern=r"^[a-z][a-z0-9-]{1,47}$")
    issuer: str
    audience: str = Field(min_length=1)
    # Every claim must equal its value (repository, ref, environment, project_path...).
    claims: dict[str, str]
    organization_id: UUID
    scopes: list[str] = Field(min_length=1)
    ttl_seconds: int = Field(default=900, ge=60, le=3600)

    @field_validator("issuer")
    @classmethod
    def https_issuer(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("the issuer must be an https URL")
        return value.rstrip("/")

    @field_validator("claims")
    @classmethod
    def constrained(cls, value: dict[str, str]) -> dict[str, str]:
        # An issuer alone would trust every repository of github.com or gitlab.com.
        if not value:
            raise ValueError("name at least one claim, such as the repository")
        return value

    @field_validator("scopes")
    @classmethod
    def known_scopes(cls, value: list[str]) -> list[str]:
        unknown = unknown_scopes(value)
        if unknown:
            raise ValueError(f"unknown scopes: {unknown}")
        return value


class WorkloadRefused(Exception):
    """The CI token is not accepted. The reason is logged, not returned to the caller."""


@dataclass(frozen=True)
class WorkloadCredential:
    trust: str
    organization_id: UUID
    scopes: frozenset[str]
    expires_at: datetime


def trust_digest(trust: WorkloadTrust) -> str:
    """Digest of what the trust accepts: issuer, audience and claims, in a canonical form.

    A credential carries the digest of its trust at issue time; when the trust is changed to
    accept other tokens, the credentials it issued before stop.
    """
    accepted = {"issuer": trust.issuer, "audience": trust.audience, "claims": trust.claims}
    canonical = json.dumps(accepted, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _audiences(claims: dict[str, Any]) -> set[str]:
    audience = claims.get("aud")
    return {audience} if isinstance(audience, str) else set(audience or [])


def match(trusts: list[WorkloadTrust], claims: dict[str, Any]) -> WorkloadTrust:
    """The trust that accepts these verified claims (issuer, audience and every claim)."""
    for trust in trusts:
        if trust.issuer != claims.get("iss") or trust.audience not in _audiences(claims):
            continue
        if all(str(claims.get(key)) == value for key, value in trust.claims.items()):
            return trust
    raise WorkloadRefused("no trust matches the token's issuer, audience and claims")


_jwks_clients: dict[str, jwt.PyJWKClient] = {}


async def _jwks_client(issuer: str) -> jwt.PyJWKClient:
    if issuer not in _jwks_clients:
        async with httpx.AsyncClient(timeout=DISCOVERY_TIMEOUT_SECONDS) as http:
            response = await http.get(f"{issuer}/.well-known/openid-configuration")
            response.raise_for_status()
            metadata = response.json()
        if metadata.get("issuer", "").rstrip("/") != issuer:
            raise WorkloadRefused("the issuer's metadata names another issuer")
        _jwks_clients[issuer] = jwt.PyJWKClient(metadata["jwks_uri"], cache_keys=True)
    return _jwks_clients[issuer]


async def verify(token: str, trusts: list[WorkloadTrust]) -> tuple[WorkloadTrust, dict[str, Any]]:
    """Verify a CI token against the trusted issuers and return the trust it matches."""
    try:
        token_issuer = str(jwt.decode(token, options={"verify_signature": False}).get("iss", ""))
    except jwt.PyJWTError as error:
        raise WorkloadRefused(f"not a JWT: {error}") from error
    # Trusts are stored without a trailing slash; the token keeps the issuer as its CI wrote it.
    issuer = token_issuer.rstrip("/")
    if issuer not in {trust.issuer for trust in trusts}:
        raise WorkloadRefused("the issuer is not trusted")
    try:
        client = await _jwks_client(issuer)
        key = await run_in_threadpool(client.get_signing_key_from_jwt, token)
        claims: dict[str, Any] = jwt.decode(
            token,
            key.key,
            algorithms=SIGNING_ALGORITHMS,
            issuer=token_issuer,
            options={"verify_aud": False, "require": ["exp", "iat", "iss", "aud"]},
        )
    except (jwt.PyJWTError, httpx.HTTPError, KeyError) as error:
        raise WorkloadRefused(f"verification failed: {error}") from error
    claims["iss"] = issuer
    return match(trusts, claims), claims


def issue(trust: WorkloadTrust, secret: str, now: float | None = None) -> tuple[str, datetime]:
    """A credential of this API for the trust, valid for its ttl."""
    issued = int(now if now is not None else time.time())
    expires = issued + trust.ttl_seconds
    payload = {
        "type": TOKEN_TYPE,
        "sub": f"workload:{trust.name}",
        "org": str(trust.organization_id),
        "scopes": sorted(trust.scopes),
        "trust": trust_digest(trust),
        "iat": issued,
        "exp": expires,
    }
    token = CREDENTIAL_PREFIX + jwt.encode(payload, secret, algorithm="HS256")
    return token, datetime.fromtimestamp(expires, UTC)


def read(credential: str, secret: str, trusts: list[WorkloadTrust]) -> WorkloadCredential | None:
    """The workload credential sent as an API key, or None if it is not a valid one.

    The credential is checked against the trusts configured now: a trust that was removed,
    moved to another organization or changed to accept other tokens (issuer, audience, claims)
    stops its credentials at once, a shorter lifetime stops those issued for longer, and scopes
    removed from it are removed from them.
    """
    if not credential.startswith(CREDENTIAL_PREFIX):
        return None
    try:
        payload = jwt.decode(
            credential[len(CREDENTIAL_PREFIX) :],
            secret,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub", "org", "scopes", "type", "trust"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != TOKEN_TYPE:
        return None
    name, organization_id = str(payload["sub"]).removeprefix("workload:"), UUID(payload["org"])
    trust = next(
        (
            t
            for t in trusts
            if t.name == name
            and t.organization_id == organization_id
            and trust_digest(t) == payload["trust"]
            and payload["exp"] - payload["iat"] <= t.ttl_seconds
        ),
        None,
    )
    scopes = frozenset(payload["scopes"]) & frozenset(trust.scopes) if trust else frozenset()
    if not scopes:
        return None
    return WorkloadCredential(
        trust=name,
        organization_id=organization_id,
        scopes=scopes,
        expires_at=datetime.fromtimestamp(payload["exp"], UTC),
    )
