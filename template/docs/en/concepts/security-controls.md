# Security controls and compliance

This page maps the controls of ISO/IEC 27001:2022 (Annex A) and the SOC 2 Trust Services
Criteria to what a generated project implements, and to the file or test that shows it. It is
evidence for an audit, not a certification: ISO 27001 certifies an organization's management
system and SOC 2 reports on an organization's controls. The software supports the controls
below; the organization that runs it remains responsible for the rest (last section).

Every line names its evidence. Tests run in the project's pipeline, so the evidence is checked
on every change, not written once.

## Access control and identity

| Control | ISO 27001 | SOC 2 | What the project does | Evidence |
| --- | --- | --- | --- | --- |
| Segregation of tenants | A.8.3 | CC6.1, C1.1 | PostgreSQL row level security on every table, for an application login that owns nothing and cannot bypass it; without a principal no row is visible | `app/db/tenancy.py`, `tests/test_segregation_postgres.py` |
| Least privilege | A.5.15, A.8.2 | CC6.3 | Roles of an organization checked in the database as well as in the code; API keys limited to scopes; members' conversations private even to administrators | `app/db/tenancy.py`, `tests/test_rbac_teams.py`, `tests/test_api_keys_postgres.py` |
| Privileged access | A.8.2 | CC6.1 | Work outside row level security goes through `system_session(reason)` on the owner login, each use logged with its reason | `app/db/session.py` (logger `app.db.system`) |
| Retrieval tenancy | A.8.3 | C1.1 | Every vector carries its tenant; a search without a reader returns nothing | `app/services/rag/tenancy.py`, `tests/test_rag_tenancy.py`, `tests/test_rag_search_scope.py` |
| Authentication | A.8.5 | CC6.1, CC6.2 | Single sign-on with OpenID Connect (code flow with PKCE, verified ID token, accounts matched only by verified addresses); no token in URLs | `app/core/oidc.py`, `tests/test_sso.py` |
| Authentication information | A.5.17 | CC6.1 | Passwords hashed with Argon2id, older hashes upgraded at sign-in; sign-in time does not reveal registered addresses; API key secrets stored as a keyed hash | `app/core/security.py`, `app/core/api_keys.py`, `tests/test_security.py`, `tests/test_services.py` |
| Session protection | A.8.5, A.8.26 | CC6.1, CC6.7 | Browser tokens in HttpOnly, SameSite cookies, out of reach of page scripts; cookie-authenticated writes and WebSockets accepted only from trusted origins (CSRF) | `app/core/session_cookies.py`, `tests/test_session_cookies.py` |
| Machine identities | A.5.16, A.8.5 | CC6.2 | CI jobs authenticate with their platform's OpenID Connect token against a configured trust (issuer, audience, repository, branch); credentials expire within the hour and stop when their trust is removed, moved or changed | `app/core/workload_identity.py`, `tests/test_workload_identity.py` |
| API key lifecycle | A.5.18 | CC6.2 | Per organization, with scopes, expiry, rotation with a grace period, revocation and rate limits | `app/services/api_key.py`, `tests/test_api_keys.py` |

## Cryptography and data protection

| Control | ISO 27001 | SOC 2 | What the project does | Evidence |
| --- | --- | --- | --- | --- |
| Secrets at rest | A.8.24 | CC6.1, C1.1 | Connector credentials and tokens encrypted with dedicated, rotatable keys (`DATA_ENCRYPTION_KEYS`), separate from the token signing key | `app/core/crypto.py`, `tests/test_data_encryption.py` |
| Data leakage in logs | A.8.12 | CC6.7 | Messages, extra fields and exception text redacted; fields named like secrets dropped, in any spelling, plural, fused or versioned form (`newPassword`, `X-API-Key`, `S3_SECRET_KEY`, `refresh_tokens`, `apiKeyHash`, `api_key_v2`), inside models, dataclasses, mappings, header pairs and name/value entries too; passwords in URLs (empty user included) and HTTP Basic credentials redacted in text, and in values of any type (exceptions, bytes, URL objects); the patterns run in linear time on hostile text; model representations never show secret columns; SQL parameters hidden outside debug mode | `app/core/logging.py`, `tests/test_log_trap.py`, `tests/test_model_repr.py` |
| Data leakage in the API | A.8.12 | CC6.7 | Maintainer notes kept out of the published API reference | `tests/test_openapi_contract.py` |
| Transport | A.8.24 | CC6.7 | TLS terminated by Traefik with Let's Encrypt in the production stack, with HSTS; Content Security Policy and the other security headers on the API and the frontend | `docker-compose.prod.yml`, `app/core/middleware.py`, `frontend/security-headers.conf` (with a frontend) |

## Logging, monitoring and records

| Control | ISO 27001 | SOC 2 | What the project does | Evidence |
| --- | --- | --- | --- | --- |
| Event logging | A.8.15 | CC7.2 | JSON logs with request id, trace and span ids | `app/core/logging.py`, `tests/test_observability.py` |
| Audit trail | A.8.15, A.5.33 | CC7.2 | Creation, rotation, revocation and refused uses of API keys recorded; the application can add entries but not read, change or delete them; an action that cannot be audited is rolled back | `app/core/audit.py`, `tests/test_segregation_postgres.py` |
| Monitoring | A.8.16 | CC7.2 | Prometheus metrics, behind a bearer token when deployed; OpenTelemetry traces; liveness and readiness probes that report a status per dependency, the reason of a failure going to the log | `app/core/telemetry.py`, `app/api/routes/v1/health.py`, `tests/api/test_health.py` |

## Development, change and supply chain

| Control | ISO 27001 | SOC 2 | What the project does | Evidence |
| --- | --- | --- | --- | --- |
| Secure configuration | A.8.9 | CC7.1 | A staging or production start refuses development defaults and stand-ins for secrets (the values of `.env.example`, of the Kubernetes secret and of `garage/development.env` included), secrets shorter than 32 characters (16 for an access key id), with fewer than 8 different, or made mostly of well-known words (look-alike substitutions included), the project name, runs of neighbouring characters, one repeated piece or doubled characters (`is_weak_secret`; Garage secrets checked by `cmd garage-bootstrap`; every setting named like a secret is checked or exempted with a reason), debug mode, metrics without a token and token signing algorithms other than HMAC; the production Compose stack stops when a required value is missing, keeps the Valkey password off the command line and trusts forwarded client addresses only from the proxy network | `app/core/config.py`, `tests/test_production_settings.py`, `docker-compose.prod.yml` |
| Change management | A.8.32 | CC8.1 | The API contract is versioned; drift and breaking changes fail the pipeline; migrations tested up and down | `scripts/openapi.py`, `tests/test_migrations.py`, CI workflow |
| Secure coding | A.8.28 | CC8.1 | Security lint rules (Ruff `S`, from Bandit) with reviewed exceptions | `backend/pyproject.toml` |
| Security testing | A.8.29 | CC7.1 | Attack tests against a real PostgreSQL, log trap, authentication tests | the tests named above |
| Technical vulnerabilities | A.8.8 | CC7.1 | Dependency audits (pip-audit, and bun audit with a frontend), container image scan (Trivy); failures stop the pipeline | CI workflow |
| Secrets in the repository | A.8.12 | CC6.1 | The whole history is scanned for secrets (gitleaks) | CI workflow |
| Supply chain | A.5.21 | CC6.8, CC9.2 | Software bill of materials (CycloneDX); CI actions pinned to commit SHAs, uv, Bun and oasdiff pinned to a release (oasdiff checked against its published checksum), dependencies installed from the lock files only (`uv sync --locked`, `bun install --frozen-lockfile`); Dependabot (GitHub) or Renovate (GitLab) propose updates after a seven-day cooldown; agent skills pinned to the digest of their content and scanned before installation | CI workflow, `.github/dependabot.yml` or `renovate.json`, `scripts/agent_skills.py`, `skills.lock.toml` |

## What remains with the organization

The software does not cover, and an auditor will ask about:

- policies, risk assessment, roles and training (ISO 27001 clauses 4 to 10, Annex A.5 and A.6);
- access reviews, joiners and leavers in the identity provider, multi-factor authentication
  (configured at the provider used for single sign-on);
- storage and rotation of secrets in production (a secret manager rather than files), key
  custody for `DATA_ENCRYPTION_KEYS`;
- backups, restore tests and business continuity (A.8.13, A.5.30; SOC 2 availability);
- log retention, alerting and incident response (A.5.24 to A.5.28; SOC 2 CC7.3 to CC7.5);
- penetration tests and supplier assessments of the model providers and hosting;
- base images pinned by digest (`image:tag@sha256:...`): the generator cannot fetch digests,
  so the images are pinned by tag. Renovate adds the digests on its first run; with Dependabot,
  pin them once from a machine with registry access (`CONTRIBUTING.md`, Container images) and
  Dependabot keeps tag and digest current.
