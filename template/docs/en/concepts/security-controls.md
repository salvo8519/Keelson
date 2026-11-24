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
| Machine identities | A.5.16, A.8.5 | CC6.2 | CI jobs authenticate with their platform's OpenID Connect token against a configured trust (issuer, audience, repository, branch); credentials expire within the hour | `app/core/workload_identity.py`, `tests/test_workload_identity.py` |
| API key lifecycle | A.5.18 | CC6.2 | Per organization, with scopes, expiry, rotation with a grace period, revocation and rate limits | `app/services/api_key.py`, `tests/test_api_keys.py` |

## Cryptography and data protection

| Control | ISO 27001 | SOC 2 | What the project does | Evidence |
| --- | --- | --- | --- | --- |
| Secrets at rest | A.8.24 | CC6.1, C1.1 | Connector credentials and tokens encrypted with dedicated, rotatable keys (`DATA_ENCRYPTION_KEYS`), separate from the token signing key | `app/core/crypto.py`, `tests/test_data_encryption.py` |
| Data leakage in logs | A.8.12 | CC6.7 | Messages, extra fields and exception text redacted; fields named like secrets dropped; SQL parameters hidden outside debug mode | `app/core/logging.py`, `tests/test_log_trap.py` |
| Data leakage in the API | A.8.12 | CC6.7 | Maintainer notes kept out of the published API reference | `tests/test_openapi_contract.py` |
| Transport | A.8.24 | CC6.7 | TLS terminated by Traefik with Let's Encrypt in the production stack, with HSTS; Content Security Policy and the other security headers on the API and the frontend | `docker-compose.prod.yml`, `app/core/middleware.py`, `frontend/security-headers.conf` (with a frontend) |

## Logging, monitoring and records

| Control | ISO 27001 | SOC 2 | What the project does | Evidence |
| --- | --- | --- | --- | --- |
| Event logging | A.8.15 | CC7.2 | JSON logs with request id, trace and span ids | `app/core/logging.py`, `tests/test_observability.py` |
| Audit trail | A.8.15, A.5.33 | CC7.2 | Creation, rotation, revocation and refused uses of API keys recorded; the application can add entries but not read, change or delete them; an action that cannot be audited is rolled back | `app/core/audit.py`, `tests/test_segregation_postgres.py` |
| Monitoring | A.8.16 | CC7.2 | Prometheus metrics, OpenTelemetry traces, liveness and readiness probes | `app/core/telemetry.py`, `app/api/routes/v1/health.py` |

## Development, change and supply chain

| Control | ISO 27001 | SOC 2 | What the project does | Evidence |
| --- | --- | --- | --- | --- |
| Secure configuration | A.8.9 | CC7.1 | A production start refuses development defaults for secrets | `app/core/config.py`, `tests/test_production_settings.py` |
| Change management | A.8.32 | CC8.1 | The API contract is versioned; drift and breaking changes fail the pipeline; migrations tested up and down | `scripts/openapi.py`, `tests/test_migrations.py`, CI workflow |
| Secure coding | A.8.28 | CC8.1 | Security lint rules (Ruff `S`, from Bandit) with reviewed exceptions | `backend/pyproject.toml` |
| Security testing | A.8.29 | CC7.1 | Attack tests against a real PostgreSQL, log trap, authentication tests | the tests named above |
| Technical vulnerabilities | A.8.8 | CC7.1 | Dependency audits (pip-audit, and bun audit with a frontend), container image scan (Trivy); failures stop the pipeline | CI workflow |
| Secrets in the repository | A.8.12 | CC6.1 | The whole history is scanned for secrets (gitleaks) | CI workflow |
| Supply chain | A.5.21 | CC6.8, CC9.2 | Software bill of materials (CycloneDX); agent skills pinned to the digest of their content and scanned before installation | CI workflow, `scripts/agent_skills.py`, `skills.lock.toml` |

## What remains with the organization

The software does not cover, and an auditor will ask about:

- policies, risk assessment, roles and training (ISO 27001 clauses 4 to 10, Annex A.5 and A.6);
- access reviews, joiners and leavers in the identity provider, multi-factor authentication
  (configured at the provider used for single sign-on);
- storage and rotation of secrets in production (a secret manager rather than files), key
  custody for `DATA_ENCRYPTION_KEYS`;
- backups, restore tests and business continuity (A.8.13, A.5.30; SOC 2 availability);
- log retention, alerting and incident response (A.5.24 to A.5.28; SOC 2 CC7.3 to CC7.5);
- penetration tests and supplier assessments of the model providers and hosting.
