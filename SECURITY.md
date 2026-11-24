# Security policy

## Reporting a vulnerability

Report vulnerabilities privately, through GitHub private vulnerability reporting (Security tab of the repository) or by email to the
maintainer listed in `GOVERNANCE.md`. Include the affected template version (the `_commit` in
`.copier-answers.yml` of a generated project), the answers used, and the steps to reproduce.
You will receive an acknowledgement within five working days.

Do not open a public issue for a vulnerability.

## Scope

- The template and the projects it generates with their default configuration.
- The tooling of this repository.

Vulnerabilities in the upstream templates are reported to their maintainers as well; Keelson
applies the fix and records it in `PROVENANCE.md`.

## Practices

- Generated projects refuse insecure default secrets in production.
- Third-party agent skills are official, pinned to a commit and read before they are added.
- Dependencies are locked; the pipeline of generated projects includes a security scan.
