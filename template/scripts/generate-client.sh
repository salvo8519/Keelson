#! /usr/bin/env bash
# Regenerate the frontend API client from the backend's OpenAPI document
# (adapted from the official FastAPI template).
set -euo pipefail

cd "$(dirname "$0")/.."
(cd backend && ENVIRONMENT=local uv run python -c \
  "import app.main, json; print(json.dumps(app.main.app.openapi()))") > frontend/openapi.json
cd frontend
bun run generate-client
bun run lint
