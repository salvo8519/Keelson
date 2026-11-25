# Tenancy and API keys

Keelson projects serve several organizations from one deployment. This page explains how
their data is kept apart and how other systems get access.

## Organizations and the active organization

Each user has a personal organization and can belong to others, with a role: owner, admin,
member or viewer. The frontend lets the user choose the active organization; every request
carries it in the `X-Organization-Id` header, and the backend checks the membership before
using it.

The database separates tenants by membership: a user's requests can read the rows of every
organization the user belongs to, whichever is active. The active organization decides where
new organization data goes and what the screens list; it is not a second boundary inside the
user's own organizations. API keys are the exception: a key acts for its one organization only.

## Isolation in the database

The database enforces the separation itself, so a forgotten filter in the code cannot leak
another tenant's rows.

**Two logins.** `POSTGRES_USER` owns the tables and runs the migrations. Requests use a second
login, `POSTGRES_APP_USER`, created by the migrations: it does not own the tables, cannot bypass
row level security and acts through a restricted role.

**Who acts, in every transaction.** Authentication states the principal of the request, and
every transaction of the application login writes it into transaction-local settings:

| Principal | Set by | Sees |
| --- | --- | --- |
| User | a JWT or a session | their own rows, their organizations' rows, the people they share an organization with |
| Organization | the active organization, after the membership check | where new organization data is written; the database boundary stays the user's memberships |
| Service | an API key | its organization's data, not members' private conversations; it cannot manage keys |
| None | no authentication | nothing: the policies fail closed |

**Policies per table and command.** Highlights:

- a conversation is private to its author unless shared; owners and administrators of an
  organization see aggregates (tool usage, ratings), never members' chats;
- roles are checked in the database too: only owners and administrators manage API keys,
  members and invitations; an administrator manages members and viewers only, the owner role
  is granted by an owner, and an organization's creator becomes its owner once;
- viewers read an organization's knowledge bases, documents and sync sources; owners,
  administrators and members change them. A document is written only with a knowledge base
  the user may write, whatever organization the row names;
- what a row grants cannot be rewritten by the application login: column privileges keep a
  user's role and administrator flag, a conversation's author, organization and public demo
  flag, and the author of a share, as they were created;
- tables are opened to the application login one by one, with their policies: a table created
  later, by a migration or by the pgvector store at run time, stays closed until a migration
  segregates it;
- the audit log is append-only for the application: an entry names its own actor and cannot
  be read, changed or deleted by it.

**System sessions.** Work that has no user yet or spans tenants uses the owner login through
`system_session(reason)`, and every use is logged with its reason on the `app.db.system`
logger: sign-in, registration and token lookups, the platform administration (after the admin
check, naming the admin), the command line and background workers. Workers act across
organizations by design, so their code filters explicitly.

**Tests.** The policies are listed in `app/db/tenancy.py`. A test fails when a table is neither
covered by a policy nor closed with a reason, so a new table cannot be forgotten. Attack tests
run against a real PostgreSQL with the application login: no principal, another user, another
organization, a member against an owner's data, forged writes and an API key.

**Limits.** The principal is set by the application on its own connection. SQL injected into
the application login could change those settings and act as someone else; the defence is the
one the code already follows (SQLAlchemy with bound parameters, no SQL built from input). A
context signed by the application and verified in the database would remove this limit and is
a possible future step.

## Knowledge bases and vectors

A knowledge base is personal (its owner only), of an organization (its members) or of the
application (every user). Who reads a knowledge base is not who changes it: a personal one is
changed by its owner, an organization's by its owners, administrators and members, and the
application's by platform administrators only, through the system session, because every
tenant reads it. A collection belongs to one knowledge base (a unique index), and the columns
that decide its tenant (scope, organization, owner, collection) cannot be changed by the
application login.

The vector store has no row level security of its own, so it gets two barriers:

1. **Which collections.** A search reaches only the collections of the knowledge bases the user
   can see in the active organization; any other name is answered as not found. The agent
   resolves its collections on the server from the conversation, never from the model or the
   client, and drops an organization the user no longer belongs to.
2. **Which vectors.** Every vector carries the tenant of its knowledge base (`user:<id>`,
   `org:<id>` or `app`), and every search states the tenants of its reader: a filter in
   Qdrant (a tenant index, Qdrant's multitenancy pattern), a `WHERE` clause in pgvector. A
   search without a reader returns nothing. Only the command line, for administration, may
   search every tenant.

Deleting a document removes its vectors, and deleting a knowledge base removes its documents
and its collection: deleted content is no longer retrievable. Local sync
(`POST /rag/sync/local`) reads only inside `RAG_LOCAL_SYNC_ROOT` and feeds only the
application's knowledge bases; without that setting it is refused in staging and production.

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

A request authenticated by a key acts as a service principal of the key's organization (see
the table above), under row level security like a user request. To protect a route with a key:

```python
from fastapi import Depends

from app.api.deps import CurrentApiKey, require_api_scopes


@router.post("/agent/run", dependencies=[Depends(require_api_scopes("agent:run"))])
async def run(principal: CurrentApiKey) -> ...:
    ...
```

New scopes are added to `SCOPES` in `app/core/api_keys.py`, with a description shown in the
interface.
