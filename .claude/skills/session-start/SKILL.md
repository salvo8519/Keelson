---
name: session-start
description: Opens a working session on Keelson with full context. Use when a session begins, or when the maintainer asks where the project stands.
---

<!-- Generated from .agents/skills/session-start/SKILL.md by scripts/sync_agents.py. Edit the source, not this file. -->

Talk to the maintainer in their preferred language (`CLAUDE.local.md`); everything written to the repository or to GitLab is in English, without icons.

## Produces
A briefing (branch, uncommitted work, latest hand-over, open merge requests, skills state), a short plan, and, once the maintainer chooses, a branch for the chosen issue.

## Steps
1. **State.** `git status`, `git log --oneline -5`, the current branch and its issue number (`<type>/<issue>-<slug>`).
2. **Hand-over.** Read the latest entry of `.agents/journal/` for this branch, otherwise the latest overall. Its Not done and Next step are the default continuation.
3. **Skills.** Run `uv run just skills-check`. If it fails, run `uv run just skills` (official component skills, pinned in `skills.lock.toml`).
4. **Upstream.** Read `PROVENANCE.md`, Keelson changes: the issue may already be partly covered.
5. **Plan.** Propose the next step of the hand-over, or up to three issues of the current milestone, marking which can run in parallel (disjoint paths).
6. **Wait for the maintainer's choice**, then create the branch `<type>/<issue>-<slug>` from an up-to-date `main` (one git worktree per issue when sessions run in parallel).

## Stop and ask
Until the maintainer chooses, change no file.

## Report
What was read and found, the plan, and what could not be checked.
