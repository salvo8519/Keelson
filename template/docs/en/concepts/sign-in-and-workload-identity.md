# Sign-in and workload identity

People sign in with a password or through their company's identity provider. CI jobs and other
systems authenticate with an API key or, without any stored secret, with the identity their
platform gives them. Every path ends in the same place: a principal that the database
segregation applies to (see [Tenancy and API keys](tenancy-and-api-keys.md)).

## Passwords

Passwords are hashed with Argon2id. Hashes of earlier versions (bcrypt) are verified and
replaced at the next sign-in. A sign-in with an unknown address does the same hashing work, so
response times do not reveal which addresses are registered.

## The browser session

In the browser, the access and refresh tokens are HttpOnly cookies set by the API: no script
in the page can read them, so a script injected into the page cannot steal the session.

| Cookie | Sent to | Lifetime |
| --- | --- | --- |
| `access_token` | every API request | the access token's (`ACCESS_TOKEN_EXPIRE_MINUTES`) |
| `refresh_token` | `/api/v1/auth/session` only | the refresh token's (`REFRESH_TOKEN_EXPIRE_MINUTES`) |

Both are `SameSite=Lax`, and `Secure` outside local development. When the access token
expires, the frontend renews the session once from the refresh cookie and repeats the request;
the new tokens are set as cookies, never returned to the page. Signing out removes the cookies.

Because a browser attaches cookies by itself, a request authenticated by a cookie that changes
something (any method but GET, HEAD and OPTIONS), and a WebSocket opened with a cookie, must
come from an origin listed in `CORS_ORIGINS`; otherwise it is refused (cross-site request
forgery). Programs (scripts, services, CI) send `Authorization: Bearer` or an API key, which a
browser never attaches by itself, and are not affected.

## Single sign-on

Any OpenID Connect provider can be offered on the sign-in page: Google, Microsoft Entra ID,
Keycloak, Okta, Auth0 or a company's own issuer. Providers are configured at run time, as a
JSON list in `OIDC_PROVIDERS`; an empty list turns single sign-on off. Projects generated
without a frontend do not include it.

| Field | Meaning |
| --- | --- |
| `name` | Identifier in URLs and on the user's identity; do not rename a provider in use |
| `label` | Text of the button on the sign-in page |
| `issuer` | The provider's issuer URL; its metadata is read from `/.well-known/openid-configuration` |
| `client_id`, `client_secret` | The application registered with the provider |
| `scopes` | Default `openid email profile` |
| `trust_email` | `true` for a company directory (Entra ID, Keycloak) that vouches for its addresses; requires `email_domains` |
| `email_domains` | Optional: only these domains may sign in with this provider |

Register `<PUBLIC_API_URL>/api/v1/oauth/<name>/callback` as the redirect URI with the provider.

```bash
OIDC_PROVIDERS='[
  {"name": "entra", "label": "Microsoft",
   "issuer": "https://login.microsoftonline.com/<tenant-id>/v2.0",
   "client_id": "...", "client_secret": "...", "trust_email": true,
   "email_domains": ["example.com"]},
  {"name": "keycloak", "label": "Company account",
   "issuer": "https://sso.example.com/realms/<realm>",
   "client_id": "...", "client_secret": "...", "trust_email": true,
   "email_domains": ["example.com"]}
]'
```

`GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` remain as a shortcut for a Google provider.

How a sign-in works:

1. The button sends the user to the provider (authorization code flow with PKCE).
2. The provider sends the user back. The ID token is verified: signature with the provider's
   published keys, issuer, audience, expiry and nonce.
3. The user is found by the provider's identity. The first time, an address must be verified
   by the provider (or come from a trusted directory, for its own domains). If no account has
   that address, one is created with a personal organization. An existing account is linked
   only when it has no password, no other identity and no platform role, and the token says
   the address is verified; otherwise the sign-in is refused and the user signs in with their
   password. Accounts are never taken over through an address someone else registered.
4. The browser returns to the frontend with a code valid once, for one minute, and stored only
   as a hash. The frontend exchanges it for the session tokens. Tokens never appear in a URL,
   where browser history, proxies and server logs would keep them.

The user signs in once, at the provider. Multi-factor authentication, password policies and
account locking are those of the provider.

## Workload identity for CI

GitHub Actions and GitLab CI give every job a short-lived token, signed by their issuer, that
names the repository, the branch and the workflow. A trust in `WORKLOAD_IDENTITIES` says which
of those tokens may act for which organization, with which API key scopes. The job exchanges
its token for a credential of this API, valid for a few minutes, and sends it like an API key.
No secret is stored in the CI.

| Field | Meaning |
| --- | --- |
| `name` | Identifier of the trust, in logs |
| `issuer` | `https://token.actions.githubusercontent.com` or `https://gitlab.com` (or your GitLab) |
| `audience` | The audience the job requests; use the URL of this API |
| `claims` | Claims that must match exactly; at least one, such as the repository. Prefer immutable ids (`repository_id`, `project_id`): a repository name can be taken by another account after a rename, a transfer or a deletion |
| `organization_id` | The organization the job acts for |
| `scopes` | API key scopes of the credential |
| `ttl_seconds` | Lifetime of the credential, 60 to 3600 (default 900) |

```bash
WORKLOAD_IDENTITIES='[
  {"name": "deploy-main", "issuer": "https://token.actions.githubusercontent.com",
   "audience": "https://api.example.com",
   "claims": {"repository_id": "123456789", "ref": "refs/heads/main"},
   "organization_id": "<uuid>", "scopes": ["agent:run"]}
]'
```

GitHub Actions:

```yaml
permissions:
  id-token: write
steps:
  - name: Call the API as this workflow
    run: |
      oidc=$(curl -sSf -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
        "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=https://api.example.com" | jq -r .value)
      credential=$(curl -sSf -X POST https://api.example.com/api/v1/auth/workload-token \
        -H "Content-Type: application/json" -d "{\"token\": \"$oidc\"}" | jq -r .credential)
      curl -sSf -H "X-API-Key: $credential" https://api.example.com/api/v1/api-keys/introspect
```

GitLab CI:

```yaml
call-api:
  id_tokens:
    API_TOKEN:
      aud: https://api.example.com
  script:
    - credential=$(curl -sSf -X POST https://api.example.com/api/v1/auth/workload-token
        -H "Content-Type: application/json" -d "{\"token\": \"$API_TOKEN\"}" | jq -r .credential)
```

For GitLab, useful claims are `project_id`, `ref`, `ref_protected` and `environment`.

A refused token gets the same answer whatever the reason; the reason is in the server log.
Every request checks its credential against the trusts configured at that moment: removing a
trust, moving it to another organization or removing scopes applies at once to credentials
already issued.
