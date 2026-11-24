# Agent skills

Coding agents work better on a library when they read guidance written by the people who
maintain it. Keelson installs those skills, and only those, for the components a project uses.

## What is installed

The file `skills.lock.toml` lists the skills of the generated project. It is rendered from your
answers: a project with Qdrant gets the Qdrant skills, a project without a frontend gets no
React skill.

| Component | Skills | Maintainer |
| --- | --- | --- |
| FastAPI | `fastapi` | FastAPI |
| Pydantic | `pydantic` | Pydantic |
| Pydantic AI | `building-pydantic-ai-agents` | Pydantic |
| LangChain, LangGraph, Deep Agents | `langchain-build-agent` | LangChain |
| Logfire | `logfire-instrumentation` | Pydantic |
| Qdrant | `qdrant-clients-sdk`, `qdrant-multitenancy`, `qdrant-search-quality` | Qdrant |
| React | `vercel-react-best-practices`, `vercel-composition-patterns` | Vercel |
| shadcn/ui | `shadcn` | shadcn |

## Two kinds of source

- **Package**: the skill ships inside the installed Python package (the
  [Library Skills](https://library-skills.io) convention used by FastAPI and Pydantic AI). It
  always matches the version you installed.
- **Git**: the skill lives in the maintainer's repository and is pinned to a commit.

Every skill is read before it is added to the lock. The `shadcn` skill runs
`npx shadcn@latest info --json` when it loads, a read-only command that describes the project.

## Commands

```bash
python scripts/agent_skills.py install   # install or refresh
python scripts/agent_skills.py check     # fails if an install is missing or changed
python scripts/agent_skills.py list      # what the lock declares
```

Installed skills go to `.agents/skills/` and `.claude/skills/`, and ignore themselves in git:
the lock is what you commit.
