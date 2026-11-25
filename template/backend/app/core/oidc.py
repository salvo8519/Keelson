"""OpenID Connect providers for sign-in (Keelson).

Upstream signs in with Google only, through Authlib. Keelson keeps Authlib and the upstream
flow, and lets any OpenID Connect provider be configured at run time: Google, Microsoft Entra
ID, Keycloak, Okta, Auth0 or a company's own issuer. They differ only in configuration:

    OIDC_PROVIDERS=[
      {"name": "entra", "label": "Microsoft",
       "issuer": "https://login.microsoftonline.com/<tenant-id>/v2.0",
       "client_id": "...", "client_secret": "...", "trust_email": true,
       "email_domains": ["example.com"]},
      {"name": "keycloak", "label": "Company account",
       "issuer": "https://sso.example.com/realms/<realm>",
       "client_id": "...", "client_secret": "...", "trust_email": true,
       "email_domains": ["example.com"]}
    ]

This module holds what can be decided without the network: the provider settings and the
rules that turn the claims of a verified ID token into an identity the application accepts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

GOOGLE_ISSUER = "https://accounts.google.com"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class OidcProvider(BaseModel):
    """An OpenID Connect provider users can sign in with."""

    # In URLs (/oauth/<name>/login) and stored with the identity: never rename one in use.
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{1,31}$")
    # Shown on the sign-in button.
    label: str = Field(min_length=1, max_length=40)
    # The provider's issuer; its metadata is read from <issuer>/.well-known/openid-configuration.
    issuer: str
    client_id: str = Field(min_length=1)
    client_secret: str = ""
    scopes: str = "openid email profile"
    # A company directory (Entra ID, Keycloak) vouches for its addresses: accept the e-mail
    # address as verified. Public providers must say so in the token (email_verified).
    trust_email: bool = False
    # Only addresses of these domains may sign in with this provider; empty allows any. Required
    # with trust_email: a directory is trusted for its own domains, not for every address.
    email_domains: list[str] = Field(default_factory=list)

    @field_validator("issuer")
    @classmethod
    def https_issuer(cls, value: str) -> str:
        parsed = urlparse(value)
        local = parsed.hostname in LOCAL_HOSTS
        if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
            raise ValueError("the issuer must be an https URL (http only for localhost)")
        return value.rstrip("/")

    @field_validator("email_domains")
    @classmethod
    def lower_domains(cls, value: list[str]) -> list[str]:
        return [domain.strip().lower().lstrip("@") for domain in value if domain.strip()]

    @model_validator(mode="after")
    def trusted_for_its_domains(self) -> "OidcProvider":
        if self.trust_email and not self.email_domains:
            raise ValueError("trust_email needs email_domains: the domains the directory owns")
        return self

    @property
    def discovery_url(self) -> str:
        return f"{self.issuer}/.well-known/openid-configuration"


def configured_providers(
    providers: list[OidcProvider], google_client_id: str = "", google_client_secret: str = ""
) -> list[OidcProvider]:
    """The configured providers, with upstream's Google settings as a shortcut."""
    result = list(providers)
    names = {provider.name for provider in result}
    if google_client_id and "google" not in names:
        result.append(
            OidcProvider(
                name="google",
                label="Google",
                issuer=GOOGLE_ISSUER,
                client_id=google_client_id,
                client_secret=google_client_secret,
            )
        )
    if len(names) != len(providers):
        raise ValueError("OIDC_PROVIDERS: provider names must be unique")
    return result


class SignInRefused(Exception):
    """The provider authenticated someone the application does not accept. ``code`` is sent
    to the frontend, which shows the reason in the user's language."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code


@dataclass(frozen=True)
class Identity:
    subject: str
    email: str
    name: str | None
    # The token itself says the address is verified (not only the provider's configuration).
    email_verified: bool = False


def verified_identity(provider: OidcProvider, claims: dict[str, Any]) -> Identity:
    """The identity in the claims of an ID token that Authlib has already verified
    (signature, issuer, audience, expiry, nonce)."""
    subject = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().lower()
    if not email and provider.trust_email:
        # Entra ID sends the sign-in name, an address, when no e-mail claim is configured.
        candidate = str(claims.get("preferred_username") or "").strip().lower()
        email = candidate if "@" in candidate else ""
    if not subject or not email:
        raise SignInRefused("no_email", "the ID token has no e-mail address")
    claimed = claims.get("email_verified") in (True, "true")
    verified = claimed or provider.trust_email
    if not verified:
        raise SignInRefused("email_unverified", "the e-mail address is not verified")
    domain = email.rsplit("@", 1)[-1]
    if provider.email_domains and domain not in provider.email_domains:
        raise SignInRefused("domain_not_allowed", "the e-mail domain is not allowed")
    name = str(claims.get("name") or "").strip() or None
    return Identity(subject=subject, email=email, name=name, email_verified=claimed)
