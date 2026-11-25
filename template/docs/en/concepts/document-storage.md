# Document storage

Documents of the knowledge bases and files attached in the chat are stored objects. The
database records whose each object is, where its bytes are and what they must hash to; the
bytes live in a storage backend. Documents and chat files reference an object by its id,
never by a path.

## Backends

One access point (`app/services/file_storage.py`) offers two interchangeable backends:

| Backend | Where the bytes go | Use |
| --- | --- | --- |
| `local` | Under `MEDIA_DIR` on the server's disk | Development, a single server |
| `s3` | A bucket of any S3-compatible service: Garage, AWS S3, Cloudflare R2, Ceph, MinIO | Production, several servers, Kubernetes |

`STORAGE_BACKEND` chooses the backend of new objects. When it is not set, the backend is `s3`
if `S3_ENDPOINT` or `S3_ACCESS_KEY` is set, and `local` otherwise. Each object records its own
backend, so objects written before a change stay readable where they are until they are
migrated.

| Setting | Default | Meaning |
| --- | --- | --- |
| `S3_ENDPOINT` | AWS | Endpoint of the S3 service |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | empty | Credentials, from the environment only; never logged |
| `S3_BUCKET` | the project name with hyphens | Bucket of the objects |
| `S3_REGION` | `us-east-1` | Region (`garage` for Garage) |
| `S3_ADDRESSING_STYLE` | `auto` | `path` for Garage, MinIO and Ceph without wildcard DNS |

Avatars of users and organizations are not stored objects: they stay on the local disk.

## Keys and ownership

Every object has exactly one owner, an organization or a user, and its key follows from it:

- `org/<organization_id>/<object_id>` for an organization's object: documents of
  organization knowledge bases and documents uploaded by an administrator;
- `user/<user_id>/<object_id>` for a personal object: chat files and documents of personal
  knowledge bases.

The key never derives from the content. Two tenants who upload the same file get two
objects: a store shared by content would tell a tenant that another one holds a file, and
would tie the erasure of one tenant's data to the others. The owner prefix also makes erasure
simple: the content of a deleted user or organization is everything under its prefix.

Object ids are random version 4 UUIDs.

## Who can read an object

The `stored_objects` table is under row level security like every other table (see
[Tenancy and API keys](tenancy-and-api-keys.md)). A personal object is visible to its user
only; an organization's object to the organization's members and to its API keys. Another
user or organization cannot read, list, change or delete it, and cannot create an object in
someone else's name: the row is written before the bytes, so the database refuses the upload
before anything is stored.

Downloads go through the API. The route finds the document or the chat file, then reads the
object through the request's session: an object the principal may not see is not found. The
content is then streamed from the backend. With `S3_PRESIGNED_DOWNLOADS=true`, an object on
S3 is answered instead with a redirect to a presigned URL valid for `S3_PRESIGN_TTL_SECONDS`
(five minutes by default), issued only after the same check; `S3_ENDPOINT` must then be
reachable from the browser.

## Integrity

The SHA-256 of an object is computed while it is written, in chunks: no backend reads a whole
file into memory, and the size limit is enforced on the way, so an oversized upload leaves
nothing behind. Objects larger than one part (8 MiB) are sent to S3 as multipart uploads;
an upload that fails is aborted.

The hash serves integrity, not deduplication: a migration verifies every copy against it.

## Moving objects to another backend

To move from the local disk to S3 (or back):

1. Configure the target and set `STORAGE_BACKEND` to it, so new uploads go there.
2. Run `uv run <project> cmd migrate-storage --from local --to s3`. The command walks the
   objects of the source in batches (`--batch-size`, `--limit`) and queues one task per
   object on the workers; `--inline` copies in the command's own process instead.
3. Each task marks the object as migrating, copies it in streaming, reads the copy back and
   compares its SHA-256 with the recorded one, then points the object at the copy in one
   transaction. Readers are never blocked: until the switch they read the original.
4. Run `uv run <project> cmd storage-cleanup` (it also runs every day on the workers) to
   remove the copies left on the source.

A copy that does not match the hash is deleted and the object stays where it was. Objects
recorded before stored objects existed have no hash yet: the migration computes it.

The cleanup also removes objects that no document or chat file references any more, and,
with reconciliation (the default), content under `org/` and `user/` that no object records:
bytes of an upload whose transaction rolled back, and the content of deleted users and
organizations. Content younger than 24 hours is left alone, as an upload may still be in
progress.

## Garage in Docker Compose

The development and production Compose stacks run [Garage](https://garagehq.deuxfleurs.fr),
an S3-compatible object store by Deuxfleurs, in its own container, pinned to a release:

- `garage/garage.toml` configures one node with one copy of every object. It holds no secret:
  Garage reads `GARAGE_RPC_SECRET` and `GARAGE_ADMIN_TOKEN` from its environment.
- `garage-init` runs `cmd garage-bootstrap` at every start: through Garage's administration
  API it assigns the node a role in the layout, imports the application's key, creates the
  bucket and grants the key access to it. Every step is skipped when already done. The API
  waits for it.
- `garage/storage.env` points the API and the workers at Garage. The keys come from
  `garage/development.env` in development (published values, for a developer's machine only),
  from `.env.prod-local` with `make prod-local` (generated at random), and from
  `backend/.env` in production, where `GARAGE_RPC_SECRET`, `GARAGE_ADMIN_TOKEN`,
  `S3_ACCESS_KEY` and `S3_SECRET_KEY` are required. Garage imports keys in its own format:
  `GK` followed by 24 hexadecimal digits, and a secret of 64 hexadecimal digits.

Kubernetes manifests deploy no object store: they expect an external S3-compatible service,
configured in the ConfigMap and the Secret.

### Licence of Garage

Garage is licensed under the GNU Affero General Public License version 3. The project runs it
as a separate service, unmodified, and talks to it over the S3 protocol; it does not link or
include Garage's code, so the project's own licence is unaffected. The AGPL's obligations,
offering the source code to the users of the service, apply to whoever modifies Garage and
lets others use the modified version over a network. Any other S3-compatible service can
take its place without a change to the code.

## Limits

- An interrupted copy is not resumed: the partial multipart upload is aborted and the next run
  copies the object again from the beginning. A crashed migration is claimed again after one
  hour. A lifecycle rule that removes incomplete multipart uploads is recommended on S3
  buckets.
- The original of a document in a knowledge base shared with the whole application belongs to
  the organization that uploaded it: users of other organizations can search the document but
  not download the original.
- Downgrading the database below the migration that introduced stored objects requires every
  object to be on the local disk.
