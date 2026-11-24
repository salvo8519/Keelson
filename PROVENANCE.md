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
| M0 | Kubernetes (fix) | Taskiq scheduler deployment added (one replica): upstream deployed only the worker, so scheduled jobs never ran on Kubernetes. |

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

## Re-sync procedure

1. Clone the upstream sources at the new commits.
2. Run `scripts/upstream/import_upstream.py` into an empty scratch directory, once at the
   recorded commits and once at the new ones.
3. Merge the difference between the two scratch imports into `template/` with a three-way diff
   (`git merge-file` or `diff3`), keeping the Keelson changes listed above.
4. Regenerate `copier/vstorm.yml` with `scripts/upstream/build_vstorm_context.py`.
5. Update the commits in the table above and run the full gate (`uv run just check`).
