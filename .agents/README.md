# .agents: the project's agent configuration

The single, tool-agnostic source of truth for AI agents working on Keelstone. Project-wide
instructions are in `AGENTS.md` (all agents) and `CLAUDE.md` (Claude Code specifics). The
`.claude/` folders are generated from here by `scripts/sync_agents.py`.

| Path | Content |
| --- | --- |
| `agents/<name>.md` | Roles used as subagents |
| `skills/<name>/SKILL.md` | Process workflows of this repository, in the open Agent Skills format |
| `skills/<name>/` (git-ignored) | Official component skills installed from `skills.lock.toml` by `uv run just skills` |
| `journal/` | Session hand-overs, one file per session |

## Roles

| Role | Responsibility | Writes code |
| --- | --- | --- |
| `explorer` | Locates code in the template and the upstream sources | No |
| `test-engineer` | Tests from acceptance criteria, before the code | Tests |
| `implementer` | One issue, test first, upstream code reused first | Yes |
| `reviewer` | Review against AGENTS.md, PROVENANCE.md and the issue | No |
| `simplifier` | Review lens: code that need not exist, missed reuse | No |
| `security-reviewer` | Tenancy, API keys, secrets, dependencies, CI | No |
| `docs-writer` | English documentation pages | Documentation |
| `translator` | Italian edition, with the glossary | Documentation |

## Provisional

These files are adapted from Fairmark and Wayloop. Keelstone will take its process
from Wayloop as it matures, and this folder will keep only what is specific to the template.
