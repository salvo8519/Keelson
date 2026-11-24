---
name: pre-pr
description: Runs the full gate, renders the template for the affected answers, delegates review by tier and drafts the pull request. Use before opening a pull request.
---

<!-- Generated from .agents/skills/pre-pr/SKILL.md by scripts/sync_agents.py. Edit the source, not this file. -->

Talk to the maintainer in their preferred language (`CLAUDE.local.md`); everything written to the repository or to GitHub is in English, without icons.

## Produces
A green `uv run just check`, render tests of the affected answers, a review by tier with every finding fixed, and the pull request description.

## Steps
1. **Gate.** `uv run just check`; fix and re-run until it passes.
2. **Render.** `uv run just test` (render matrix). For a change to the backend or frontend of the template, `uv run just test-generated` on the default answers.
3. **Tier** (AGENTS.md): Small needs no review agent; Substantial gets the `reviewer` and the `simplifier` lens; Security adds the `security-reviewer` and waits for the maintainer.
4. **Findings.** Fix every finding in this branch, then re-run the gate.
5. **Description.** Summary, `Closes #<n>`, acceptance criteria covered, provenance entries, documentation and translation status, tests run, risks.

## Stop and ask
A finding that needs a design decision goes to the maintainer.

## Report
Gate and test results, findings and how they were fixed, the description.
