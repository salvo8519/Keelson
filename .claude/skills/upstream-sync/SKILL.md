---
name: upstream-sync
description: Re-syncs the template with new commits of the upstream templates, keeping the Keelstone changes. Use when an upstream release fixes defects or adds features Keelstone wants.
---

<!-- Generated from .agents/skills/upstream-sync/SKILL.md by scripts/sync_agents.py. Edit the source, not this file. -->

Talk to the maintainer in their preferred language (`CLAUDE.local.md`); everything written to the repository or to GitHub is in English, without icons.

## Produces
A branch where `template/` holds the new upstream code plus every Keelstone change listed in `PROVENANCE.md`, with the commits updated.

## Steps
1. Clone both upstream sources at the commits in `PROVENANCE.md` and at the new commits.
2. Run `scripts/upstream/import_upstream.py` into two empty scratch directories (old and new).
3. For each file, merge the upstream change into `template/` with `git merge-file template/<file> <old>/<file> <new>/<file>`; resolve conflicts against the Keelstone changes table.
4. Install the new upstream generator and run `uv run just upstream-context` to regenerate `copier/vstorm.yml`.
5. Update the commits in `PROVENANCE.md`, render the defaults, compare with the upstream generator output as in the Verification section, run `uv run just check` and `uv run just test-generated`.

## Stop and ask
An upstream change that conflicts with a security-tier Keelstone change goes to the maintainer.

## Report
Upstream commits, files merged, conflicts and how they were resolved, test results.
