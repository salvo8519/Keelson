# Getting started

## Requirements

- Docker, to run the stack
- Python 3.13 and [uv](https://docs.astral.sh/uv/), to work on the backend
- [Bun](https://bun.sh/), when the project has the React frontend

## Run the stack

```bash
cp backend/.env.example backend/.env
make dev
```

`make dev` builds the backend image and starts the services with Docker Compose. `make help`
lists every command.

## Work on the backend

```bash
make install   # backend dependencies and pre-commit hooks
make test      # backend test suite
make lint      # lint and type checks
```

The tests that need PostgreSQL (row level security, API keys, migrations) run against the
database of `backend/.env` and skip themselves when it is not reachable.

## Translations

The API, the emails and the interface follow the [languages](concepts/languages.md) of the
project. `make i18n-check` fails on any backend message without a translation; in the
frontend, `bun run i18n:check` does the same.

## Documentation

This site is built with [Zensical](https://zensical.org) from `docs/`: English pages in
`docs/en`, translations in `docs/<language>`.

```bash
make docs          # every edition, strict, with the API and settings reference
make docs-serve    # live preview; DOCS_LANG=it make docs-serve for the Italian edition
make docs-check    # translations missing or out of date
```

The [API](reference/api.md) and [settings](reference/settings.md) reference pages are generated
from the code at every build, so they cannot fall behind it. A translated page records the
version of the English page it was translated from: after translating, run
`python scripts/i18n.py stamp docs/<language>/<page>.md`. CI builds the site, fails on broken
links and stale translations, and publishes it from the main branch.
