# Provenance

Keelson is assembled, not written from scratch. This file records what was imported, from where,
at which commit, and what Keelson changed on top. It is the reference for attribution
(see NOTICE and THIRD_PARTY_NOTICES.md) and for every re-sync with the upstream projects.

## Upstream sources

| Source | Licence | Commit | Commit date | Imported into |
| --- | --- | --- | --- | --- |
| [vstorm-co/full-stack-ai-agent-template](https://github.com/vstorm-co/full-stack-ai-agent-template) | MIT | `475f799f7df02738f804fa350f2de244d7331a94` | 2026-10-06 | `template/` except `template/frontend/` |
| [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) | MIT | `77e550a73bb49dd2967622c5ed11bf7a49603c93` | 2026-11-16 | `template/frontend/` |

## How the import works

`scripts/upstream/import_upstream.py` copies both sources into an empty directory:

- Upstream cookiecutter files keep their content. Two mechanical changes let Copier render them:
  the `cookiecutter.` prefix is dropped from Jinja expressions, and files that contain Jinja get
  the `.jinja` suffix.
- The upstream post-generation hook becomes `template/_post_gen.py.jinja` and runs as a Copier
  task.
- The upstream Next.js frontend is not imported; the official React frontend takes its place.
- House style: emoji and pictographic icons are replaced by plain text (or dropped), the same
  rule that `scripts/check_style.py` enforces on the repository.

`scripts/upstream/build_vstorm_context.py` writes `copier/vstorm.yml`. It runs the upstream
generator (`fastapi_gen`) on every valid combination of the Keelson questions and expresses each
of the upstream variables as a constant or as a lookup on the smallest set of questions that
determines it. The upstream derivation logic is reused, not rewritten.

### Verification of the conversion

With the default answers, the project rendered by Copier was compared file by file with the
project rendered by the upstream generator for the same options. The only differences are the
intended ones: project metadata, the Traefik service included in `docker-compose.prod.yml`
(Keelson uses `traefik_included`), and the absence of the upstream Next.js frontend.

## Keelson changes on top of the import

Each change is listed with the milestone that introduced it. Changes to imported files are kept
small and marked in the file with a `Keelson:` comment where the reason is not obvious.

| Milestone | Area | Change |
| --- | --- | --- |
| M0 | Generator | Copier configuration (`copier.yml`, `copier/vstorm.yml`), answers file, Keelson questions. |
| M0 | Licensing | `NOTICE` and `THIRD_PARTY_NOTICES.md` added to generated projects. |
| M0 | House style | Emoji and icons replaced in imported files. |
| M0 | Workers (fix) | Taskiq: task modules are loaded by the new entry point `app/worker/taskiq_worker.py`, no longer by `taskiq_app.py`; this removes the circular import found in the audit. Compose, CLI and Kubernetes point to the new entry point; regression test runs the imports in a fresh interpreter. |
| M1 | Tenancy | New `app/db/tenancy.py`: PostgreSQL row level security on `TENANT_TABLES`, a restricted role per project, and a session listener that restricts every transaction of a session bound to an organization. `get_active_organization` binds the request session (`app/api/deps.py`). Migration `k0001_tenant_row_level_security`. Tests against a real PostgreSQL in a throwaway schema, and a guard that every table with `organization_id` is isolated or exempted with a reason. |
| M1 | Users (security fix) | `PATCH /users/me` takes `UserUpdateMe` (profile fields only) instead of `UserUpdate`: upstream let a user set a new password without the current one and change their own account status. New `PATCH /users/me/password` (current password required), `DELETE /users/me`, and `POST /users` for administrators, from the official template. Tests in `tests/api/test_users.py` and `tests/test_user_password.py`. |
| M1 | API | Operation ids `<tag>-<function>` (`custom_generate_unique_id`, from the official template), so the generated TypeScript client has readable service and method names. |
| M1 | Frontend | Official React frontend connected to the Keelson API: client regenerated, vstorm authentication endpoints, roles instead of `is_superuser`, `src/lib/session.ts` (storage keys, `X-Organization-Id` on every request), Items replaced by Organizations (list, create, active organization switcher, members). Built to `dist/` and served by its own nginx container (`frontend/Dockerfile`), because the Keelson backend does not serve static files. `scripts/generate-client.sh` adapted from the official template. |
| M2 | API keys (new) | Per-organization API keys: `app/core/api_keys.py` (format, keyed hash, scopes), model, repository, service, routes `/api/v1/api-keys`, migration `k0002_api_keys` (isolated by row level security), dependencies `CurrentApiKey` and `require_api_scopes` in `app/api/deps.py`. Creation, rotation, revocation and refused uses go to the upstream audit log (`app/core/audit.py`); requests are limited per key and per organization with the upstream rate limiter (new category `api_key`). Neither upstream source has per-organization keys: the vstorm template has one static key in the settings, kept for compatibility. Frontend page `/api-keys`. Unit tests and tests against a real PostgreSQL. |
| M2 | API (operation ids) | Tags in operation ids are normalised (`api-keys` to `api_keys`), so the client method names stay readable for every service. |
| M2 | Post-generation hook (fix) | The upstream hook removed `scripts/` wholesale when the demo export is off; it now removes only the exporter, keeping `scripts/agent_skills.py` and `scripts/generate-client.sh`. Render test added. |
| M2 | Retrieval (fix) | Qdrant returns `payload=None` for points stored without one; `vectorstore.py` read it with `.get` (found by `ty`, the type checker of the generated project). |
| M0 | Kubernetes (fix) | Taskiq scheduler deployment added (one replica): upstream deployed only the worker, so scheduled jobs never ran on Kubernetes. |
| M3 | Errors (new) | Every error is a Problem Details document (RFC 9457, `application/problem+json`) with a translated `title` and `detail`, a stable `code`, `request_id` and a `Content-Language` header: `app/core/problems.py`, `app/api/exception_handlers.py` (framework errors such as 401 and 404 included). Upstream returned `{"error": {...}}`; its tests were updated to the new format. `RateLimitError` replaces the upstream `HTTPException` for 429, so the limit is reported in the same format. |
| M3 | i18n backend (new) | `app/core/i18n.py`: language of the request in a context variable, chosen in the order user preference, organization default, `Accept-Language`, default (`LanguageMiddleware`, `get_current_user`, `get_active_organization`). Babel catalogs in `app/locales` read from the `.po` files; `app/core/i18n_catalog.py` extracts the messages of every `AppException` subclass and of `N_()` and fails on untranslated ones (`make i18n-extract`, `make i18n-check`). `users.locale` and `organizations.default_locale` (migration `k0003_locales`), editable through `PATCH /users/me` and the organization update. Italian catalog with all messages. |
| M3 | Emails (i18n) | Emails are written in the recipient's saved language, otherwise in the language of the request (invitations use the organization's default): translated templates in `backend/emails/compiled/<language>/`, English fallback, link lifetimes from `PASSWORD_RESET_TTL` and `MAGIC_LINK_TTL` in `app/core/security.py` instead of a fixed `"1 hour"`. Italian templates for the transactional emails; billing and credits emails stay English (outside the Keelson profile). |
| M3 | Emails (fix) | Upstream kept the compiled emails at the project root and mounted them in Compose only: the loader found no template when the backend ran locally or on Kubernetes, and every email failed (logged, not raised). They now live in `backend/emails` and ship in the backend image; the Compose mounts are gone and `scripts/upstream/import_upstream.py` relocates the directory on re-sync. |
| M3 | Emails (fix) | The magic-link request sent the welcome template with the sign-in link; it now sends the `magic_link` template (`EmailService.send_magic_link`). |
| M3 | i18n frontend (new) | The official frontend has no i18n. `src/i18n.ts` uses `i18next` (core only: the English text is the key, `t()` is a plain function so module-level texts such as table headers and form messages are translated, and changing language reloads the page); `react-i18next`, named in the plan, was not needed. `src/locales/languages.ts` comes from the Copier answer `languages`; `src/locales/it.json` holds every key. Language switcher in the sidebar, saved in the user profile; after login the interface adopts the saved language. Every request sends `Accept-Language`. `bun run i18n:check` (`scripts/check-i18n.mjs`) fails on untranslated keys. |
| M3 | Frontend (fix) | The official frontend signed the user out on any 403. With organization roles and API key scopes a 403 is a missing permission, so only 401 ends the session now. |
| M3 | RAG status stream (security fix) | `GET /rag/status/stream` had no authentication and streamed the ingestion events (document ids and file names) of every organization from one Redis channel; its dependency also built `RAGStatusService` without the Redis client it requires, so every call failed (found by `ty`). The worker now publishes on a per-organization channel (`rag_status_channel` in `app/services/rag/config.py`) and the endpoint requires a user and streams only the active organization's channel, on the shared Redis client. Tests in `tests/test_rag_status.py`. |
| M3 | Redis client | The connection check repeated in every `RedisClient` method now goes through the existing `raw` property. |
| Review | RAG search (security fix) | `POST /rag/search` required only an authenticated user and searched any collection by name: a user of one organization could read the documents of another. It now searches only the collections of the knowledge bases the user can see in the active organization (404 otherwise). Tests in `tests/test_rag_search_scope.py`. |
| Review | Vector tenancy (new) | Second barrier inside the vector store (`app/services/rag/tenancy.py`): every vector carries the tenant of its knowledge base (`user:`, `org:`, `app`), insert and search take the tenant as a required argument, Qdrant filters on a tenant index, pgvector on a column; a search without a reader returns nothing (the agent sets the reader of each turn where its collections are resolved). The Milvus and Chroma implementations, not offered by Keelson, were removed. Tested with mocks for Qdrant and against a real PostgreSQL with pgvector. |
| Review | Agent knowledge bases (security fix) | A user removed from an organization kept searching its knowledge bases through the agent, because the organization came from the stored conversation; membership is now checked (`KnowledgeBaseService`). |
| Review | Qdrant search (fix) | `AsyncQdrantClient.search` no longer exists in qdrant-client 1.20: every search failed. It uses `query_points`. |
| Review | pgvector tables (fix) | Collection tables were named `rag_<collection>`, so the default collection `documents` mapped onto the application's `rag_documents` table and `list_collections` reported application tables. They are `vectors_<collection>`. |
| Review | Taskiq dispatch (fix) | Uploads and source syncs called Celery's `delay` on Taskiq tasks, which have no such method: with Taskiq (the default) no upload reached the worker. They use `kiq`, and the API process starts the broker as a producer. |
| Review | Emails (security fix) | User-supplied names were inserted raw into the HTML of emails (a name could carry a phishing link into an invitation), kept line breaks in the subject, and a value containing a placeholder was expanded again. Values are now HTML-escaped, one line in the subject, substituted in one pass. |
| Review | API key expiry (fix) | An expiry in the past created a dead key and a time without zone risked a naive/aware comparison; past times are refused, times without zone are UTC. |
| Review | Frontend security headers (new) | nginx serves a Content Security Policy (scripts from the same origin only, API calls only to the origin of `VITE_API_URL`, set at image build), `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, in every location. Verified in headless Chrome: login and signup render with no violation. |
| Review | Tests | The live PostgreSQL check, repeated in the row level security and API key tests, is one helper (`tests/postgres.py`). |
| M4 | Hosting | Keelson is hosted on GitHub: its own CI is GitHub Actions (`.github/workflows/ci.yml`, documentation on GitHub Pages) and generated projects default to `ci_provider: github`; the GitLab CI of generated projects stays available and tested. |
| M4 | Documentation of generated projects (new) | Upstream shipped Markdown pages only. Generated projects now have the Zensical site Keelson uses, one edition per language answer: `zensical.toml`, `i18n/it.yaml`, `docs/en` and `docs/it` (home, getting started, concepts, reference), the upstream pages moved to `docs/en/guides` (kept in English; the Italian site links to them). The API and settings reference is generated from the code at every build (`scripts/docs_reference.py`, into `.generated/`, included by the reference pages), so it cannot fall behind. `make docs`, `make docs-serve`, `make docs-check`; a `docs` job with Pages publishing in both the GitHub and the GitLab CI. New question `repository_url` (site and edit links). The tools `scripts/docs.py` and `scripts/i18n.py` have one copy, in `template/scripts`, which Keelson runs on itself through thin wrappers; the concept pages on tenancy, languages and observability have one source, in `template/docs`, included by Keelson's site. |
| M4 | API reference (new) | Scalar at `/docs` (`app/core/api_docs.py`, with `scalar-fastapi` by Scalar, MIT) replaces Swagger UI and ReDoc. White label from `brand_name` and `brand_primary_color`: title, favicon, accent, no vendor link; the mark is shared with the frontend favicon (`template/_includes/brand_mark.svg.jinja`, rendered into `app/core/brand.py` and `favicon.svg`). Telemetry, AI agent, hosted fonts, proxy and client button off; a Content Security Policy computed from the rendered page (script hashes) allows only the pinned bundle (`API_DOCS_SCALAR_JS_URL`, `@scalar/api-reference@1.83.0`) and same-origin connections. Verified in headless Chrome with the bundle served locally: two origins contacted, no policy violation. The OpenAPI description no longer claims Milvus or an MIT licence for the generated project, and documents the tenancy tags and the error format. |
| M4 | Security headers (fix) | `SecurityHeadersMiddleware` was defined upstream but never added: responses had no CSP, `X-Frame-Options` or `X-Content-Type-Options`. It is now added; responses that set their own policy keep it. |
| M4 | Logs (new) | JSON lines (`LOG_FORMAT`, `LOG_LEVEL`) with request id, trace and span ids and `extra=` fields; uvicorn records go through the same handler (`app/core/logging.py`). |
| M4 | Logs (fix) | The PII redaction filter was attached to the root logger, where it saw only records logged on the root itself, not those of named loggers. It is now on the handler, so it applies to every record. |
| M4 | Request id (fix) | `X-Request-ID` from the client was trusted as is (any length, any characters) and would reach the logs; only plain identifiers up to 128 characters are kept now. |
| M4 | Tracing (new) | OpenTelemetry over OTLP/HTTP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (`app/core/telemetry.py`): FastAPI (health and metrics excluded), SQLAlchemy, httpx, Redis; parent-based ratio sampling. Not rendered with `logfire`, which owns tracing then. Worker processes are not yet covered (M5, with context propagation across tasks). |
| M4 | Metrics (fix) | The Prometheus instrumentator used the process-wide registry, so a second `create_app()` in the same process failed with duplicated metrics. Each application has its own registry with the standard process collectors. The in-progress gauge is off: in `prometheus-fastapi-instrumentator` it ignores the registry passed to it. |
| Review | Database segregation (security, replaces M1) | M1 isolated only the tables with `organization_id`, and only while a request was bound to an organization; personal data (users, conversations, messages, files) was not enforced by the database. Now every table of the application is covered or closed with a reason (`app/db/tenancy.py`, migration `k0004_database_segregation`, which replaces `k0001`). Two logins: requests use `POSTGRES_APP_USER`, which owns nothing and cannot bypass row level security; `POSTGRES_USER` owns the tables and runs migrations and `system_session(reason)` work, logged on `app.db.system` (sign-in and token lookups, platform administration, command line, workers). Each transaction states its principal (user, organization or API key as a service) and without one sees nothing. Policies per table and command: conversations private to their author unless shared (organization admins see aggregates only), roles checked in the database for API keys, members and invitations, append-only audit log. 13 attack tests against a real PostgreSQL with the application login, and an end-to-end run of registration, organizations, conversations, knowledge bases, API keys and invitations under the application login. |
| Review | Commit before response (fix) | Database sessions were committed after FastAPI had sent the response (dependencies with `yield` run after the response by default): a commit refused by a constraint or a policy reached the client as a success, e.g. an API key returned with 201 and never stored. Session dependencies use `scope="function"`, so the commit happens before the response. |
| Review | Audit log (fix) | Entries are written without `RETURNING`, which the append-only policy refuses, and a failure now raises and rolls the action back instead of being logged and skipped (an action that cannot be audited does not happen). |
| Review | Problem Details (fix) | Error details with ids (a UUID in "not found") could not be serialised, so a 404 became a 500. Details are encoded as FastAPI encodes responses. Expected errors (not found, forbidden) no longer log a database error with a traceback. |
| Review | API contract (new) | `openapi/openapi.json` is versioned with the code: `scripts/openapi.py` exports it from the application's defaults (no `.env`, so the same on every machine) and checks it (`make openapi`, `make openapi-check`, run by `make install`). The pipeline (GitHub and GitLab) fails on drift, compares a pull request with the target branch with oasdiff (breaking changes fail) and, on GitHub, fails when the committed frontend client is not generated from the contract. The documentation site publishes it at `/openapi.json` and the reference page explains the lifecycle; `docs_reference.py` builds its pages from the same document. `info.version` is the backend package version instead of a literal. `scripts/generate-client.sh` (official template) now exports the contract and the client reads it from `openapi/`. |
| Review | API reference (fix) | Maintainer notes in route docstrings (internal reasons, file paths) were published as operation descriptions. They follow a form feed now, where FastAPI stops; a test fails when a description mentions Keelson, upstream or a source file. The committed frontend client is regenerated from the current API. |
| Review | Password hashing (from the official template) | Argon2id with `pwdlib`, as the official FastAPI template does (`password_hash`, `verify_and_update`, `DUMMY_HASH`), replaces raw bcrypt: bcrypt hashes are still verified and replaced at the next sign-in. A sign-in with an unknown address hashes the dummy value, so timing does not reveal registered addresses (the vstorm template returned at once). Hashing runs off the event loop. |
| Review | Logs (security fix) | The upstream redaction filter redacted the template and the arguments separately: `"password=%s"` lost its `%s`, formatting failed and logging printed the raw arguments, the password included, to standard error. The message is formatted first and redacted as a whole. `extra=` fields and exception text were written unredacted: they are redacted now, and fields named like secrets are dropped. Keelson API key secrets are redacted (the prefix stays). Engines hide statement parameters outside debug mode. `tests/test_log_trap.py` sends known secrets through every logging path and fails if one is written. |
| Review | Secrets at rest (improvement) | Connector credentials and MCP tokens were encrypted with a key derived from `SECRET_KEY`, the token signing key. `DATA_ENCRYPTION_KEYS` (required in production) now encrypts them, with rotation through `MultiFernet`; values written with `SECRET_KEY` or `CHANNEL_ENCRYPTION_KEY` still decrypt (`app/core/crypto.py`: `encrypt_secret`, `decrypt_secret`, `rotate_secret`). |

## Audit of the imported code (M0)

Upstream vstorm, generated with the Keelson defaults (Taskiq, Pydantic AI, Qdrant, teams with
`multi_org` tenancy, Redis, rate limiting, Traefik, Kubernetes, GitLab CI):

- Test suite: 311 passed, 4 skipped, 1 failed once the import cycle below was broken by hand
  (that test asserted the defective design). After the Keelson fix: 313 passed, 4 skipped.
- Defect: with Taskiq and RAG enabled, `app/worker/taskiq_app.py` imports the scheduled tasks
  module, which imports the RAG tasks, which import the broker from `taskiq_app`: a circular
  import that stops the application at start-up. Fixed in M0 (see the table above).
- Defect: the Kubernetes manifests have no Taskiq scheduler. Fixed in M0.
- Gaps confirmed against the plan: API keys are a single static key from the settings (no
  per-organization keys, scopes, rotation or audit); the backend has no internationalisation;
  tenant isolation relies on each repository filtering by `organization_id`, with no database
  enforcement, and the filter is optional in some repository functions
  (`if organization_id is not None`). Closed in M1 by row level security.

Official template frontend: React, TypeScript, Vite, TanStack Router and Query, Tailwind CSS,
shadcn/ui, generated API client, Playwright. It targets the official backend API, so its client
is regenerated from the Keelson OpenAPI document and its screens are aligned to the
organization model (M1).

## Not yet verified

- The Playwright end-to-end suite of the official frontend needs a running stack and a known
  administrator account; its specs were updated for the Keelson API (`items.spec.ts` removed,
  user creation through registration) but have not been run.
- The Docker images (`frontend/Dockerfile`, compose files) were not built in the environment
  where Keelson is developed, which has no Docker daemon; the generated project's pipeline
  builds them.
- The 50% milestone asks that the default project starts with `docker compose up`: for the
  same reason this was not run. What was run: the backend suite of the default project against
  PostgreSQL 16 (388 tests, row level security and API keys included), Alembic upgrade and
  downgrade, ruff, the message catalog check, and Biome, the translation check, `tsc` and the
  Vite build of the frontend.

## Re-sync procedure

1. Clone the upstream sources at the new commits.
2. Run `scripts/upstream/import_upstream.py` into an empty scratch directory, once at the
   recorded commits and once at the new ones.
3. Merge the difference between the two scratch imports into `template/` with a three-way diff
   (`git merge-file` or `diff3`), keeping the Keelson changes listed above.
4. Regenerate `copier/vstorm.yml` with `scripts/upstream/build_vstorm_context.py`.
5. Update the commits in the table above and run the full gate (`uv run just check`).
