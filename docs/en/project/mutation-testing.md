# Mutation testing

Line coverage says which code the tests run. It does not say whether the tests would notice
that code doing the wrong thing. Mutation testing measures that: a tool changes one detail of
a module (a condition negated, a constant altered, an argument dropped), runs the tests, and
expects at least one of them to fail. A change that no test notices is a *surviving mutant*:
behaviour that nothing pins down.

Keelson applies it to the modules of a generated project where a silent change becomes a
security defect.

| Module | What it decides |
| --- | --- |
| `app/core/oidc.py` | Which identities returned by an OpenID Connect provider may sign in. |
| `app/core/workload_identity.py` | Which CI tokens may act for an organization, and the credential they receive. |
| `app/core/api_keys.py` | Format, keyed hashing and scopes of API keys. |
| `app/core/crypto.py` | Encryption of secrets at rest and key rotation. |
| `app/core/logging.py` | Redaction of secrets and personal data in the logs. |
| `app/core/security.py` | Password hashing and verification (`get_password_hash`, `verify_password`, `verify_and_update_password`). |

## Running it

```bash
uv run just mutation
```

The recipe renders the template with the default answers into `.generated/mutation`, installs
[mutmut](https://github.com/boxed/mutmut) in the environment of the generated backend only,
mutates the modules above and runs the fast tests that exercise them (no PostgreSQL needed).
It takes a few minutes, so it is not part of `just check`: run it after changing one of these
modules or their tests.

On a project already rendered, point the script at its backend:

```bash
uv run python scripts/mutation.py --project <project>/backend
```

The score is printed per module. A mutant reported as a timeout was stopped by mutmut's CPU
time limit, usually on a loaded machine: run again before reading it as a result. In the
backend, `uv run mutmut results` lists the surviving
mutants and `uv run mutmut show <mutant>` prints the change of each. The list of modules and
tests lives in `scripts/mutation.py`.

## Reading a survivor

Each surviving mutant is one of two things.

- **A gap in the tests.** The change alters behaviour that matters. The answer is a test in
  `template/backend/tests/` that fails on the mutant, written as a rule of the module (for
  example, "a credential without an expiry is refused"), not as a copy of the code.
- **An equivalent or irrelevant mutant.** The change cannot be observed (`token_urlsafe(None)`
  uses the same default size), or it only alters free text, such as the reason of a refusal
  that goes to the log. These are left, and the reason is recorded.

A score of 100 percent is not the goal: tests written only to kill equivalent mutants pin the
code instead of its behaviour.

## Scores

Measured with mutmut 3.8.1 on the default answers. The first run is the test suite as it was;
the second follows the tests added from its survivors.

| Module | First run | Now |
| --- | --- | --- |
| `oidc.py` | 94 of 127 (74.0%) | 118 of 127 (92.9%) |
| `workload_identity.py` | 141 of 206 (68.4%) | 191 of 206 (92.7%) |
| `api_keys.py` | 27 of 31 (87.1%) | 29 of 31 (93.5%) |
| `crypto.py` | 23 of 35 (65.7%) | 35 of 35 (100%) |
| `logging.py` | 73 of 105 (69.5%) | 102 of 105 (97.1%) |
| `security.py`, password functions | 10 of 11 (90.9%) | 11 of 11 (100%) |
| Total | 368 of 515 (71.5%) | 486 of 515 (94.4%) |

The gaps the first run found, now covered by tests:

- a stored password in an unknown format was not tested on the sign-in path, where it must be
  refused (`verify_and_update_password`);
- a token without the `key_` tag but with the right length was not tested;
- the discovery of a CI issuer's keys, including metadata that names another issuer, had no
  test; nor did tokens without `exp`, `iat` or `aud`, credentials without an expiry, tokens
  with several audiences, or a trust found after others that do not match;
- the legacy channel key, the rotation of a value that was not encrypted, and the single-key
  helpers of `crypto.py` had no test;
- nested `extra=` fields, the exception of a JSON record and the text format of the logs were
  only checked for leaks, not for what they write;
- the Google shortcut of the OpenID Connect settings was not checked field by field; an
  `email_verified` claim sent as the string `"true"`, a sign-in name that is not an address and
  an address whose local part holds an `@` were not tested.

The run also found a defect. A CI token whose issuer ends with a slash was matched to its trust
and then always refused, because the signature check compared the issuer without the slash.
The check now uses the issuer as the token states it; the trust is still chosen on the
normalised issuer.

The 29 mutants left are equivalent or irrelevant:

| Module | Mutants | Why they survive |
| --- | --- | --- |
| `oidc.py` | 5 | Wording of refusal reasons, which go to the log. |
| `oidc.py` | 3 | `rsplit("@")` variants that read the same domain after the last `@`. |
| `oidc.py` | 1 | Default sign-in name when the claim is missing: it has no `@`, so there is no address either way. |
| `workload_identity.py` | 3 | Wording of refusal reasons, which go to the log. |
| `workload_identity.py` | 4 | Default issuer of a token or of metadata without one: refused either way. |
| `workload_identity.py` | 2 | `rstrip("XX/XX")`: differs only for an issuer that ends with `X`. |
| `workload_identity.py` | 2 | The issuer passed to the signature check: the value comes from the same token, so the check cannot fail; the trust check is the one that counts. |
| `workload_identity.py` | 4 | `cache_keys` of the key client (performance only: the key set is cached anyway), and HS256 written out where it is the default. |
| `api_keys.py` | 2 | `token_urlsafe(None)` uses 32 bytes, the size requested. |
| `logging.py` | 3 | `record.args = ""` and `ensure_ascii=None` behave as the originals; a default field name that matches no secret. |
