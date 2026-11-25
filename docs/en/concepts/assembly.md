# How Keelstone is assembled

Keelstone does not rewrite what two mature open source templates already do well. It imports
them, records what it imported, and adds what an enterprise project needs and they leave out.

## Sources

| Source | Licence | What Keelstone takes |
| --- | --- | --- |
| Full-Stack AI Agent Template (Vstorm) | MIT | Backend, organizations and roles, workers and schedulers, agent frameworks, retrieval, Docker, Kubernetes, CI, project tooling |
| Full Stack FastAPI Template (FastAPI) | MIT | React frontend |

The commits, the import procedure and every change Keelstone makes on top are recorded in
[Provenance](../project/provenance.md).

## From cookiecutter to Copier

The upstream backend template is a cookiecutter template with about two hundred variables,
derived by its own generator from a few choices. Keelstone keeps those template files as they
are and runs them with Copier, which records the answers in the project and can update it
later.

The derivation is not rewritten either. A script runs the upstream generator on every valid
combination of the Keelstone questions, more than three thousand, and writes each upstream
variable as a constant or as a lookup on the few questions that determine it. With the
default answers, the project that Copier renders is compared file by file with the one the
upstream generator renders: the only differences are the intended ones.

## What Keelstone adds

- Defects found in the audit of the imported code are fixed and covered by tests; the list is
  in [Provenance](../project/provenance.md).
- A licence trail: generated projects carry `NOTICE` and `THIRD_PARTY_NOTICES.md`.
- House style: no emoji or icons in generated files.
- The official skills of the components, selected by your answers
  ([Agent skills](agent-skills.md)).
- Render tests over a matrix of answers, and an end-to-end test that runs the generated
  backend's suite.
