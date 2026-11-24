# Generate a project

## Requirements

- Python 3.12 or later, and [uv](https://docs.astral.sh/uv/)
- Git
- Docker, to run the generated stack
- [Bun](https://bun.sh/), when the project has the React frontend

## Generate

Copier asks the questions listed in the [reference](../reference/questions.md). The
`--trust` flag lets Copier run the post-generation task that removes the files your answers
exclude and formats the code.

```bash
uvx copier copy --trust https://gitlab.com/salvo8519/keelson my_service
```

To accept every default, add `--defaults`. To set answers without prompts, add
`--data key=value` for each, for example `--data task_backend=celery`.

## Run

```bash
cd my_service
cp backend/.env.example backend/.env
make dev
```

`make dev` builds the images, starts the services and applies the database migrations. The
API reference is then at `http://localhost:8000/docs`. `make help` lists every command.

## Install the agent skills

```bash
cd backend && uv sync && cd ..
python scripts/agent_skills.py install
```

The skills of the components you chose are installed for Claude Code, Codex and the other
agents that read `.agents/skills/`. See [Agent skills](../concepts/agent-skills.md).

## Update from a newer Keelson

The file `.copier-answers.yml` records the template version and your answers. To bring in a
newer version of the template:

```bash
uvx copier update --trust
```

Copier applies the template changes as a three-way merge with your own changes.
