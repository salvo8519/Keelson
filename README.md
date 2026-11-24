<p align="center">
  <img src="docs/_shared/assets/brand/mark.svg" alt="Keelson" width="96">
</p>

<h1 align="center">Keelson</h1>

<p align="center"><strong>Enterprise FastAPI template with an agent layer.</strong><br>
Assembled from two proven open source templates, and improved where they stop.</p>

<p align="center">
  <img alt="Status: pre-release" src="https://img.shields.io/badge/status-pre--release-0B1F3A">
  <img alt="Licence: Apache-2.0" src="https://img.shields.io/badge/licence-Apache--2.0-0B1F3A">
  <img alt="Copier" src="https://img.shields.io/badge/generator-Copier-C8A24A">
  <img alt="Python 3.13" src="https://img.shields.io/badge/python-3.13-0B1F3A">
  <img alt="Documentation: English and Italian" src="https://img.shields.io/badge/docs-EN%20%7C%20IT-0B1F3A">
</p>

English | [Italiano](README.it.md)

Keelson generates a FastAPI service ready for companies: organizations as tenants, users who
belong to several of them, asynchronous and scheduled work, an agent layer with retrieval,
deployment on Docker and Kubernetes, and a development process for coding agents.

## Why Keelson

- **Assembled, not rewritten.** The backend, workers and agent layer come from the
  [Full-Stack AI Agent Template](https://github.com/vstorm-co/full-stack-ai-agent-template)
  by Vstorm; the React frontend from the official
  [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template).
  [PROVENANCE.md](PROVENANCE.md) records every import, commit and change.
- **Verified conversion.** The upstream cookiecutter template runs under Copier without being
  rewritten: its own generator derives the variables of every valid combination of answers,
  and the rendered project is compared file by file with the upstream output.
- **Isolation enforced by the database.** Organizations are separated by PostgreSQL row level
  security, on top of the repository filters: a query that forgets the filter still sees only
  the active organization. A test fails when a new table with an organization is not isolated.
- **API keys for other systems.** Per organization, with scopes, expiry, rotation with a grace
  period, revocation, rate limits and audit; stored only as a keyed hash.
- **White-label API reference, observable from day one.** Scalar at `/docs` with your brand
  and a Content Security Policy that blocks calls to third parties; JSON logs with request and
  trace ids; OpenTelemetry traces and Prometheus metrics.
- **English and Italian, end to end.** API errors are Problem Details (RFC 9457) in the
  language of the user, the organization or the request; emails follow the recipient's
  language; the interface has a language switcher. CI fails on any untranslated text.
- **Defects fixed at import.** The audit of the imported code found and fixed, each with a
  regression test: a circular import that stopped Taskiq projects at start-up, a missing
  scheduler on Kubernetes, a profile endpoint that changed passwords without the current one,
  an unauthenticated stream that exposed every organization's file names, and emails that were
  never sent outside Docker Compose.
- **Built for coding agents.** Instructions, roles and process skills, plus the official skills
  of FastAPI, Pydantic, LangChain, Qdrant and the React stack, selected by your answers and
  pinned.

## Quick start

```bash
uvx copier copy --trust https://github.com/salvo8519/keelson my_service
cd my_service
cp backend/.env.example backend/.env
make dev
```

The questions and their defaults are in the
[reference](docs/en/reference/questions.md). Later versions of the template come in with
`uvx copier update --trust`.

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

## Documentation

The documentation site is built with Zensical in English and Italian: getting started,
architecture of a generated project, how Keelson is assembled, agent skills.

## Development of the template

```bash
uv sync --all-groups
uv run just check            # house style, YAML, tooling, translations, render tests
uv run just test-generated   # render the defaults and run the generated backend's suite
uv run just skills           # install the official component skills for agents
```

See [AGENTS.md](AGENTS.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Apache License 2.0 (see [LICENSE](LICENSE) and [NOTICE](NOTICE)). Keelson includes code from
two MIT-licensed templates; their notices are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and are carried into every generated project.
The licence grants no right to use the Keelson name or logo.
