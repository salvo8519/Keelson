# Run with `uv run just <recipe>` (just is installed by uv).

# The Python of the repository's own tooling (the template has its own configuration).
py_paths := "scripts tests template/scripts"
# Where `just render` writes the default project.
render_dir := ".generated/default"

default:
    @just --list

# Full local gate: run before every pull request (CI runs the same checks).
check: style yaml python skills-lock agents i18n test
    @echo "All checks passed."

# House style: no icons or emoji anywhere in the repository, the template included.
style:
    python scripts/check_style.py

# Every YAML file parses.
yaml:
    python scripts/check_yaml.py

# Python of the tooling: lint, format, strict types.
python:
    ruff check {{py_paths}}
    ruff format --check {{py_paths}}
    mypy

# The skills lock of the repository matches the one in the template.
skills-lock:
    python scripts/skills_lock.py --check

# Claude Code mirrors generated from .agents/.
agents:
    python scripts/sync_agents.py --check

# Italian translations current against their English source.
i18n:
    python scripts/i18n.py check
    DOCS_ROOT=template python template/scripts/i18n.py check

# Translation status of every page.
i18n-status:
    python scripts/i18n.py status

# Render tests of the template (answer matrix, seconds per combination).
test:
    python -m pytest -m "not generated"

# Render the default project and run its own test suite (minutes).
test-generated:
    python -m pytest -m generated

# Mutation testing of the security-critical modules of the default project (minutes, not in check).
mutation *args:
    python scripts/mutation.py {{args}}

# Render the template with the default answers into .generated/default.
render:
    rm -rf {{render_dir}}
    copier copy --trust --defaults --vcs-ref HEAD . {{render_dir}}

# Install the official component skills pinned in skills.lock.toml.
skills:
    python template/scripts/agent_skills.py install --lock skills.lock.toml

# The installed component skills match skills.lock.toml.
skills-check:
    python template/scripts/agent_skills.py check --lock skills.lock.toml

# Findings of the content scan of the installed component skills (exit 1 on a blocking one).
skills-scan:
    python template/scripts/agent_skills.py scan --lock skills.lock.toml

# Regenerate copier/vstorm.yml (needs the upstream generator: see PROVENANCE.md).
upstream-context python="python":
    {{python}} scripts/upstream/build_vstorm_context.py --out copier/vstorm.yml

# Duplicated code in the repository's tooling (jscpd).
dup:
    npx --yes jscpd@4.0.5 --config .jscpd.json {{py_paths}} template/scripts

# Format the repository's tooling.
fmt:
    ruff check --fix {{py_paths}}
    ruff format {{py_paths}}

# Build both documentation sites (English and Italian), strict.
docs:
    python scripts/docs.py build

# Live preview of the documentation: `just docs-serve` or `just docs-serve it`.
docs-serve lang="en":
    python scripts/docs.py serve --lang {{lang}}

# Technical changelog from Conventional Commits.
changelog:
    git-cliff -o CHANGELOG.md

# Preview of the release notes built from the fragments in changes/.
release-notes:
    towncrier build --draft --version Unreleased
