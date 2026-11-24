<p align="center">
  <img src="docs/_shared/assets/brand/mark.svg" alt="Keelson" width="96">
</p>

<h1 align="center">Keelson</h1>

<p align="center"><strong>A FastAPI service for companies, ready on day one.</strong><br>
Tenants segregated by the database, single sign-on, an API contract and an agent layer,
each guarded by tests.</p>

<p align="center">
  <img alt="Status: pre-release" src="https://img.shields.io/badge/status-pre--release-0B1F3A">
  <img alt="Licence: Apache-2.0" src="https://img.shields.io/badge/licence-Apache--2.0-0B1F3A">
  <img alt="Copier" src="https://img.shields.io/badge/generator-Copier-C8A24A">
  <img alt="Python 3.13" src="https://img.shields.io/badge/python-3.13-0B1F3A">
  <img alt="Documentation: English and Italian" src="https://img.shields.io/badge/docs-EN%20%7C%20IT-0B1F3A">
</p>

English | [Italiano](README.it.md)

Starting a service for companies means solving the same problems before the first feature:
keeping each customer's data apart, signing in through their identity provider, giving other
systems controlled access, publishing an API that does not break its clients, and passing a
security review. Keelson generates a FastAPI project where these are already done, verified by
tests that run in its pipeline, and leaves your team the part that is specific to you.

One command produces a backend, a React frontend, background and scheduled workers, an agent
layer with retrieval, deployment to Docker and Kubernetes, and documentation in English and
Italian.

## What is already done

**Each company's data stays its own, enforced by the database.**
PostgreSQL row level security covers every table, for an application login that cannot bypass
it. Every transaction states who acts (a user, an organization, an API key); without that, no
row is visible. Members' conversations stay private even to their organization's
administrators, and roles are checked in the database as well as in the code. Attack tests
against a real PostgreSQL try to cross every boundary. The vector store has its own tenant
filter, so retrieval never returns another tenant's documents.

**People and systems sign in the way companies expect.**
Single sign-on with any OpenID Connect provider (Microsoft Entra ID, Google, Keycloak, Okta),
configured at run time, with no second login. Passwords hashed with Argon2id. API keys per
organization, with scopes, expiry, rotation and audit. CI jobs on GitHub Actions or GitLab CI
call the API with their own identity, with no secret stored in the CI.

**An API contract that does not break its clients.**
The OpenAPI document is versioned with the code. The pipeline fails when it drifts from the
code, when a pull request contains a breaking change, or when the frontend client is not
regenerated from it. A white-label reference (Scalar) is served at `/docs`, and errors follow
RFC 9457 in the user's language.

**Ready for a security review.**
Secrets never reach the logs, and a test sends known secrets through every logging path to
prove it. Secrets stored in the database use their own rotatable keys. The pipeline scans the
history for secrets, audits backend and frontend dependencies, scans the container image,
runs security lint rules and produces a software bill of materials. The skills given to
coding agents are pinned to the digest of their content and scanned before installation.

**Observable and deployable.**
JSON logs with request and trace ids, OpenTelemetry traces, Prometheus metrics, health probes,
background work with Taskiq, Celery or ARQ and a scheduler, Docker Compose and Kubernetes
manifests.

**Built to be maintained with coding agents.**
Instructions, roles and process skills for Claude Code, Codex, Copilot and Cursor, plus the
official skills of FastAPI, Pydantic, LangChain, Qdrant and the React stack, selected by your
answers.

## Quick start

```bash
uvx copier copy --trust https://github.com/salvo8519/keelson my_service
cd my_service
cp backend/.env.example backend/.env
make dev
```

Keelson uses [Copier](https://copier.readthedocs.io): it asks a few questions, renders the
project, and records your answers. When Keelson improves, `uvx copier update --trust` brings
the changes into your project and merges them with your own, so a project does not stay at the
version it was generated from. The questions and their defaults are in the
[reference](docs/en/reference/questions.md).

## What you choose

| Question | Options |
| --- | --- |
| Frontend | React (Vite, TanStack, shadcn/ui), none |
| Task queue | Taskiq, Celery, ARQ |
| Agent framework | Pydantic AI, LangGraph, LangChain, Deep Agents, Pydantic Deep |
| LLM provider | OpenAI, Anthropic, Google, OpenRouter, OpenAI-compatible (on-premise), all |
| Vector database | Qdrant, pgvector, none |
| CI | GitHub Actions, GitLab CI |
| Kubernetes | yes, no |

## How it is verified

Every change to the template renders projects and runs their checks: the backend suite
against a real PostgreSQL (database segregation and migrations included, where a skipped test
counts as a failure), the frontend build and translations, the documentation build, the API
contract and the generated client. The review of the code Keelson builds on found defects
that are fixed, each with a regression test. Among them: commits that reached the client as
successes after failing, access tokens placed in redirect URLs, a log filter that could print
passwords, accounts linked through unverified e-mail addresses, and a search that returned
another organization's documents. [PROVENANCE.md](PROVENANCE.md) lists every change.

## Documentation

The documentation site is built with Zensical in English and Italian: getting started,
concepts (tenancy, sign-in, API keys, languages, observability), the API and settings
reference generated from the code, and how Keelson is assembled.

## Development of the template

```bash
uv sync --all-groups
uv run just check            # house style, YAML, tooling, translations, render tests
uv run just test-generated   # render the defaults and run the generated project's checks
uv run just skills           # install the official component skills for agents
```

See [AGENTS.md](AGENTS.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## Built on

Keelson stands on two open source templates and keeps their work visible. The backend, the
workers and the agent layer come from the
[Full-Stack AI Agent Template](https://github.com/vstorm-co/full-stack-ai-agent-template) by
Vstorm; the React frontend from the official
[Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template). Both are
MIT-licensed. Keelson imports them at recorded commits, converts the first to Copier without
rewriting it, and adds the segregation, identity, contract, security and language layers
described above. [How Keelson is assembled](docs/en/concepts/assembly.md) explains the method.

## Licence

Apache License 2.0 (see [LICENSE](LICENSE) and [NOTICE](NOTICE)). The notices of the two
MIT-licensed templates are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and are carried
into every generated project. The licence grants no right to use the Keelson name or logo.
