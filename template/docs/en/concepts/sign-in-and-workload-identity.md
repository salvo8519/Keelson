# Sign-in and workload identity

People sign in with a password or through their company's identity provider. CI jobs and other
systems authenticate with an API key or, without any stored secret, with the identity their
platform gives them. Every path ends in the same place: a principal that the database
segregation applies to (see [Tenancy and API keys](tenancy-and-api-keys.md)).

## Passwords

Passwords are hashed with Argon2id. Hashes of earlier versions (bcrypt) are verified and
replaced at the next sign-in. A sign-in with an unknown address does the same hashing work, so
response times do not reveal which addresses are registered.

Registration does not reveal them either: it answers `202 Accepted` with the same message for
a new address and for one that already has an account. Nothing is created for a known address,
and its owner receives an e-mail with links to sign in and to reset the password. Signing in
afterwards with the password just chosen still tells a known address from a new one: closing
that needs e-mail verification before the first sign-in.

## E-mail addresses

An account records whether its user proved control of its address (`email_verified`): by
following a link sent to it (a confirmation, a password reset, a sign-in link) or by signing in
with a provider that verified it. A user changes the address in two steps:
`POST /api/v1/users/me/email` sends a confirmation link to the new address, and the address
changes only when the link is followed (`POST /api/v1/auth/email/confirm`). `PATCH
/api/v1/users/me` does not change it. The link is valid for one hour and once: it names the
address it replaces, so it stops working when the address changes, and it is void after a
password change or a sign-out from every device. An address already used by another account
is refused when the change is requested and again when it is confirmed. An address set by a
platform administrator is not confirmed.

Single sign-on relies on this: an account is never left on an address its user does not
control, waiting for the owner of that address to use it. For accounts whose address was
never confirmed, a password reset or a sign-in link to the address also removes the external
identity of the account, so its holder cannot sign in to it again. Accounts created before
this check start unconfirmed: a user who signs in through a provider and resets the password
signs in with the password afterwards.

## The browser session

In the browser, the access and refresh tokens are HttpOnly cookies set by the API: no script
in the page can read them, so a script injected into the page cannot steal the session.

| Cookie | Sent to | Lifetime |
| --- | --- | --- |
| `access_token` | every API request | the access token's (`ACCESS_TOKEN_EXPIRE_MINUTES`) |
| `refresh_token` | `/api/v1/auth/session` only | the refresh token's (`REFRESH_TOKEN_EXPIRE_MINUTES`) |

Both are `SameSite=Lax`, and `Secure` outside local development. When the access token
expires, the frontend renews the session once from the refresh cookie and repeats the request;
the new tokens are set as cookies, never returned to the page. Signing out removes the cookies
and ends the session (see below).

Because a browser attaches cookies by itself, a request authenticated by a cookie that changes
something (any method but GET, HEAD and OPTIONS), and a WebSocket opened with a cookie, must
come from an origin listed in `CORS_ORIGINS`; otherwise it is refused (cross-site request
forgery). Programs (scripts, services, CI) send `Authorization: Bearer` or an API key, which a
browser never attaches by itself, and are not affected.

Signing in and signing out set or remove cookies before anyone is authenticated, so they are
refused when the browser names another site in `Origin` or `Referer`: a page elsewhere cannot
sign the browser into an account of its choice (login CSRF). Programs send neither header.

## Ending sessions

Every access and refresh token carries the session version of its user (`ver`, the
`token_epoch` column). A request, a refresh and a WebSocket handshake are refused when the
version of their token is not the user's current one. The version is raised, ending every
session issued before, by:

- a password change (the browser that made it receives new cookies and stays signed in);
- a password reset, and a password set by a platform administrator;
- a deactivation (a reactivated account does not get its old sessions back);
- `POST /api/v1/auth/logout-all`, signing out of every device.

A sign-in starts a session, with an id (`sid`) that every refresh token of the session
carries. A refresh rotates the token: the client receives a new refresh token, and the one it
presented is recorded in Redis as exchanged. A token exchanged once and presented again means
that someone else holds a copy, so the whole session ends (reuse detection, RFC 9700, section
4.14.2) and every token of it is refused, the latest one included. Tabs of one browser share the
refresh cookie and may renew together: a token presented again within 10 seconds of its
exchange (`REUSE_GRACE`) is renewed once more, in the same session. Refresh tokens issued before
sessions had an id are refused: their users sign in again once.

Signing out (`POST /api/v1/auth/session/logout` in the browser, `POST /api/v1/auth/logout`
with the refresh token for programs) ends that session only, with every refresh token it
rotated through: the session id is kept in Redis for the lifetime of a refresh token, and a
refresh in that session is refused. A token copied before a rotation therefore ends with the
session. The access tokens of the session are not checked against the list: they expire on
their own, which is why `ACCESS_TOKEN_EXPIRE_MINUTES` may not exceed 60 in staging and
production. When Redis does not answer, a refresh fails rather than renew a session that may
have ended.

A WebSocket checks its session again before every turn of a chat: a connection whose session
version changed since the handshake, or whose user was deactivated, is closed (code 4001).

The session version only grows: the database refuses an update that lowers `token_epoch` (a
trigger, `app/db/tenancy.py`), so no write can bring back the sessions it ended.

Refreshing a session is limited per user (20 every 15 minutes by default, category `refresh`),
not per address: users behind one network address do not share a limit with each other or with
failed sign-ins. An invalid refresh token counts against the per-address limit of the sign-in
routes.

An access token issued by a platform administrator to act as a user (impersonation) names the
administrator and their session version in the `act` claim. While it is used, every log record
carries `acting_admin_id`, and every audit entry records it in its details. Every request, every
WebSocket handshake and every turn of a chat checks the administrator as well: the token stops
working when the administrator loses the platform role, is deactivated or signs out of every
device.

Requests authenticated by a cookie are accepted from the origins in `CORS_ORIGINS` only. When
the browser sends an `Origin` header, it decides alone: `Origin: null` (a sandboxed frame, a
redirect across sites) and an empty value are refused, whatever the `Referer` says. The
`Referer` is read only when no `Origin` was sent.

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
   where browser history, proxies and server logs would keep them. The code works only in the
   browser that came back from the provider, which also received a short HttpOnly cookie: a
   code sent to someone else signs nobody in (login CSRF).

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
