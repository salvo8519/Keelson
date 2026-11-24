# Tenancy and API keys

Keelson projects serve several organizations from one deployment. This page explains how
their data is kept apart and how other systems get access.

## Organizations and the active organization

Each user has a personal organization and can belong to others, with a role: owner, admin,
member or viewer. The frontend lets the user choose the active organization; every request
carries it in the `X-Organization-Id` header, and the backend checks the membership before
using it.

## Isolation in the database

Repositories filter their queries by organization. PostgreSQL row level security adds a second,
independent barrier:

- once a request has resolved its active organization, its database session is bound to it;
- every transaction of a bound session runs under a restricted role whose policies show and
  accept only that organization's rows;
- a query that forgets the filter returns nothing from other organizations, and an insert for
  another organization is refused by the database.

The isolated tables are listed in `app/db/tenancy.py`. A test fails when a table with an
`organization_id` column is neither isolated nor exempted with a reason, so a new table cannot
be forgotten.

## Knowledge bases and vectors

A knowledge base is personal (its owner only), of an organization (its members) or of the
application (every user). The vector store has no row level security of its own, so it gets
two barriers:

1. **Which collections.** A search reaches only the collections of the knowledge bases the user
   can see in the active organization; any other name is answered as not found. The agent
   resolves its collections on the server from the conversation, never from the model or the
   client, and drops an organization the user no longer belongs to.
2. **Which vectors.** Every vector carries the tenant of its knowledge base (`user:<id>`,
   `org:<id>` or `app`), and every search states the tenants of its reader: a filter in
   Qdrant (a tenant index, Qdrant's multitenancy pattern), a `WHERE` clause in pgvector. A
   search without a reader returns nothing. Only the command line, for administration, may
   search every tenant.

## API keys

An organization can create keys for other systems. Owners and administrators manage them on
the API keys page or at `/api/v1/api-keys`.

| Property | How it works |
| --- | --- |
| Format | `key_` and 12 characters (the prefix, shown in the interface) followed by a secret |
| Storage | Only an HMAC of the secret with the server's `SECRET_KEY`; the token is shown once |
| Scopes | Each key holds a set of scopes; routes require them with `require_api_scopes` |
| Expiry | Optional date after which the key stops working |
| Rotation | A replacement key with the same scopes; the old one works for a grace period |
| Revocation | Immediate |
| Limits | Requests are limited per key and per organization |
| Audit | Creation, rotation, revocation and refused uses are recorded in the audit log |

A request authenticated by a key acts on the key's organization, under the same row level
security as a user request. To protect a route with a key:

```python
from fastapi import Depends

from app.api.deps import CurrentApiKey, require_api_scopes


@router.post("/agent/run", dependencies=[Depends(require_api_scopes("agent:run"))])
async def run(principal: CurrentApiKey) -> ...:
    ...
```

New scopes are added to `SCOPES` in `app/core/api_keys.py`, with a description shown in the
interface.
