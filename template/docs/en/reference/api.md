# API

Every endpoint of the API, grouped by tag, generated from the code at every build of this site.
The interactive reference, with schemas and requests you can send, is at `/docs` on a running
instance (local, development and staging environments). Errors follow the
[Problem Details format](../concepts/languages.md#errors).

## The contract

The OpenAPI document is kept in the repository, in `openapi/openapi.json`, and published with
this site at `/openapi.json`. It is the contract of the API:

| Step | What happens |
| --- | --- |
| Export | `cd backend && uv run python ../scripts/openapi.py export` writes it from the code, with the default settings, so it is the same on every machine |
| Review | A change to the API shows up in the pull request as a change to this file |
| Drift | The pipeline fails when the file does not match the code (`openapi.py check`) |
| Breaking changes | The pipeline compares it with the target branch with oasdiff and fails on a breaking change |
| Client | The frontend client is generated from it (`scripts/generate-client.sh`), and the pipeline fails when the committed client is out of date |
| Version | `info.version` is the version of the backend package in `backend/pyproject.toml` |

A breaking change (a removed endpoint or field, a new required parameter, a narrower type)
goes to a new version of the API under a new prefix, such as `/api/v2`, while `/api/v1`
keeps working until its clients have moved.

--8<-- ".generated/docs/en/reference/api.md"
