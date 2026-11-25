# Contributing to Keelstone

Thank you for helping. Keelstone is a template: every change is judged by the projects it
generates, so a change to `template/` is tested on a rendered project.

## Set up

```bash
uv sync --all-groups
uv run pre-commit install
uv run just skills        # optional: official skills for coding agents
```

## Work on an issue

1. Pick or open an issue on GitHub, in a milestone.
2. Create a branch `<type>/<issue>-<slug>` from `main` (types: feat, fix, docs, refactor, test,
   build, ci, chore).
3. Before writing code for the template, look for it in the two upstream sources recorded in
   `PROVENANCE.md`. Import first; write new code only where neither source covers the need.
4. Record every change to an imported file in the table of `PROVENANCE.md`.
5. Write the test first where it pays: a render test in `tests/`, or a test of the generated
   backend in `template/backend/tests/`.
6. Run `uv run just check`, and `uv run just test-generated` for changes to the backend or
   frontend of the template.
7. Open a pull request with the template in `.github/pull_request_template.md`. Commits follow
   Conventional Commits, in English; the pull request is squash-merged.

## Documentation

English under `docs/en/` is the source. Change the Italian page under `docs/it/` in the same
pull request and stamp it: `uv run python scripts/i18n.py stamp docs/it/<page>.md`. A
user-facing change adds a fragment in `changes/`.

## House style

No emoji, icons or decorative symbols in any file, commit or pull request. Corporate, precise
English. `uv run just style` checks the repository and the render tests check generated
projects.

## Pinned versions

Every tool and action is pinned, in the repository and in generated projects. Dependabot
(`.github/dependabot.yml`) proposes updates for the repository's actions, its Python tooling
and the template's frontend packages, each release after a seven-day cooldown. It cannot see
the pins inside the template: the commit SHAs of the actions in
`template/.github/workflows/ci.yml.jinja` and the tool versions in `copier.yml`
(`uv_version`, `bun_version`, `oasdiff_version`, `garage_image`). Update those by hand: take
the commit of a release tag with `git ls-remote https://github.com/<owner>/<repo>
refs/tags/<tag>` (the `^{}` line for an annotated tag) and keep the version in the comment.
`tests/test_render.py` keeps the uv and Bun versions of this pipeline equal to the template's.

## Re-sync with the upstream templates

Follow `PROVENANCE.md`, Re-sync procedure, or the `/upstream-sync` skill.
