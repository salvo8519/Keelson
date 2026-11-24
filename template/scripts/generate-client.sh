#! /usr/bin/env bash
# Regenerate the frontend API client from the API contract (adapted from the official FastAPI
# template): export openapi/openapi.json from the code, then generate and lint the client.
set -euo pipefail

cd "$(dirname "$0")/.."
(cd backend && uv run python ../scripts/openapi.py export)
cd frontend
bun run generate-client
bun run lint
