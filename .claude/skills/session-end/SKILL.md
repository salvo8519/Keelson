---
name: session-end
description: Closes a working session on Keelstone so that any agent can resume it. Use when the session is over, before switching issue, or before the context runs out.
---

<!-- Generated from .agents/skills/session-end/SKILL.md by scripts/sync_agents.py. Edit the source, not this file. -->

Talk to the maintainer in their preferred language (`CLAUDE.local.md`); everything written to the repository or to GitHub is in English, without icons.

## Produces
A green gate, a journal hand-over, a commit and a pull request.

## Steps
1. **Gate.** `uv run just check`. Fix what belongs to the issue; otherwise record the failure under Not done and open the pull request as a draft.
2. **Scope.** `git diff origin/main...HEAD --stat`: every file belongs to the branch's issue.
3. **Provenance.** Every change to an imported file under `template/` has its row in `PROVENANCE.md`.
4. **Release note.** A user-facing change adds `changes/<issue>.<type>.md`.
5. **Journal.** Write `.agents/journal/<YYYY-MM-DD>-<branch-slug>.md` from `_template.md`: Done (with commit hashes), Not done (and its risk), decisions, learnings, next step. Facts only, no secrets.
6. **Commit and push.** Conventional Commit in English, signed off; `git push -u origin <branch>`.
7. **Pull request.** Title as the Conventional Commit summary; description with Summary, `Closes #<n>`, tests run, provenance entries, risks; draft if the gate failed.

## Stop and ask
Security-tier changes (authentication, tenancy, API keys, secrets) wait for the maintainer's approval before merge.

## Report
Pull request status, what remains, the very next step.
