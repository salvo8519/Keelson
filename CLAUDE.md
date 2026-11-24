# CLAUDE.md

@AGENTS.md

## Claude Code specifics

- Never use icons, emoji or decorative symbols, in files or in replies about this project.
- Talk to each person in the language they prefer: read `CLAUDE.local.md` if it exists. Write
  everything that goes into the repository in English.
- Roles live in `.agents/agents/`. Delegate instead of doing everything in the main context;
  at most three agents run in parallel, and the main session is the orchestrator.
- Plan before multi-file changes; keep diffs small and focused on one issue.
- When a design choice is ambiguous, ask the maintainer instead of picking one.
- Before writing new code for the template, search both upstream sources (`PROVENANCE.md`).

## Skills

Process skills (`.agents/skills/`, mirrored to `.claude/skills/`): `/session-start`,
`/session-end`, `/pre-pr`, `/upstream-sync`.

Component skills from the maintainers of the libraries we use (FastAPI, Pydantic, Pydantic AI,
LangChain and LangGraph, Qdrant, React) are installed with `uv run just skills`; the list and
the pinned commits are in `skills.lock.yaml`.

## Session protocol

Begin with `/session-start`, end with `/session-end`. The journal in `.agents/journal/` is how
the next session, of any agent, knows where this one stopped.
