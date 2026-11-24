"""Install the agent skills published by the maintainers of the project's components.

The skills to install are listed in ``skills.lock.toml`` at the project root. Two sources:

* ``git``: a skill folder in a repository, pinned to a commit. Fetched once into a cache.
* ``package``: a skill bundled inside an installed Python package (the Library Skills
  convention, https://library-skills.io): it follows the version of the package you use.

Each skill is copied to ``.agents/skills/<name>/`` (read by Codex, Copilot, Cursor and others)
and mirrored to ``.claude/skills/<name>/`` (Claude Code). Installed folders ignore themselves in
git: the lock file is what you commit.

    python scripts/agent_skills.py install          # install or refresh every skill
    python scripts/agent_skills.py check            # exit 1 if an install is missing or stale
    python scripts/agent_skills.py list             # what the lock file declares

Standard library only, so it runs before the project environment exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path.cwd()
TARGETS = (Path(".agents") / "skills", Path(".claude") / "skills")
MARKER = ".skill-source.json"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "agent-skills"


class SkillError(RuntimeError):
    """A skill could not be resolved from its declared source."""

    def __init__(self, subject: str, problem: str) -> None:
        super().__init__(f"{subject}: {problem}")


@dataclass(frozen=True)
class Skill:
    name: str
    path: str
    maintainer: str
    license: str
    repository: str | None = None
    commit: str | None = None
    package: str | None = None
    python: str | None = None
    note: str | None = None

    @property
    def source_id(self) -> str:
        if self.repository:
            return f"{self.repository}@{self.commit}:{self.path}"
        return f"package:{self.package}:{self.path}"


def load(lock: Path) -> list[Skill]:
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    skills = [Skill(**entry) for entry in data.get("skill", [])]
    for skill in skills:
        if bool(skill.repository) == bool(skill.package):
            raise SkillError(skill.name, "declare either repository+commit or package")
        if skill.repository and not skill.commit:
            raise SkillError(skill.name, "a git source needs a pinned commit")
    names = [s.name for s in skills]
    if len(names) != len(set(names)):
        raise SkillError("skills.lock.toml", "skill names must be unique")
    return skills


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _from_git(skill: Skill) -> Path:
    assert skill.repository and skill.commit
    checkout = CACHE / hashlib.sha256(skill.repository.encode()).hexdigest()[:16] / skill.commit
    source = checkout / skill.path
    if not (source / "SKILL.md").is_file():
        checkout.mkdir(parents=True, exist_ok=True)
        if not (checkout / ".git").exists():
            _git("init", "-q", cwd=checkout)
            _git("remote", "add", "origin", skill.repository, cwd=checkout)
        _git(
            "fetch",
            "-q",
            "--depth",
            "1",
            "--filter=blob:none",
            "origin",
            skill.commit,
            cwd=checkout,
        )
        _git("sparse-checkout", "set", "--no-cone", f"/{skill.path}/", cwd=checkout)
        _git("checkout", "-q", "FETCH_HEAD", cwd=checkout)
    if not (source / "SKILL.md").is_file():
        raise SkillError(skill.name, f"no SKILL.md at {skill.path} in {skill.repository}")
    return source


def _from_package(skill: Skill) -> Path:
    assert skill.package
    python = skill.python or sys.executable
    code = (
        "import importlib, os, sys; "
        "m = importlib.import_module(sys.argv[1]); "
        "print(os.path.dirname(m.__file__))"
    )
    result = subprocess.run(
        [python, "-c", code, skill.package], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise SkillError(
            skill.name,
            f"package {skill.package!r} is not importable with {python}; "
            "install the project dependencies first",
        )
    source = Path(result.stdout.strip()) / skill.path
    if not (source / "SKILL.md").is_file():
        raise SkillError(skill.name, f"{skill.package} does not ship {skill.path}")
    return source


def _digest(folder: Path) -> str:
    h = hashlib.sha256()
    files = (p for p in folder.rglob("*") if p.is_file() and p.name not in (MARKER, ".gitignore"))
    for file in sorted(files):
        h.update(file.relative_to(folder).as_posix().encode())
        h.update(file.read_bytes())
    return h.hexdigest()[:16]


def install(skills: list[Skill]) -> None:
    for skill in skills:
        source = _from_git(skill) if skill.repository else _from_package(skill)
        for target_root in TARGETS:
            target = ROOT / target_root / skill.name
            if target.exists() and not (target / MARKER).exists():
                raise SkillError(
                    str(target), "exists and was not installed by this tool; not touched"
                )
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(source, target, symlinks=False)
            (target / ".gitignore").write_text("*\n", encoding="utf-8")
            marker = {"source": skill.source_id, "digest": _digest(target)}
            (target / MARKER).write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
        print(f"installed {skill.name:<34} {skill.source_id}")


def check(skills: list[Skill]) -> int:
    problems = []
    for skill in skills:
        for target_root in TARGETS:
            target = ROOT / target_root / skill.name
            marker_file = target / MARKER
            if not marker_file.is_file():
                problems.append(f"{target}: not installed")
                continue
            marker = json.loads(marker_file.read_text(encoding="utf-8"))
            if marker.get("source") != skill.source_id:
                problems.append(
                    f"{target}: installed from {marker.get('source')}, lock says {skill.source_id}"
                )
            elif marker.get("digest") != _digest(target):
                problems.append(f"{target}: changed by hand since install")
    if problems:
        print("Agent skills out of date (run: python scripts/agent_skills.py install):")
        print("\n".join(f"  {p}" for p in problems))
        return 1
    print(f"{len(skills)} agent skills installed and current.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["install", "check", "list"])
    parser.add_argument("--lock", type=Path, default=Path("skills.lock.toml"))
    args = parser.parse_args(argv)
    try:
        skills = load(args.lock)
        if args.command == "install":
            install(skills)
            return 0
        if args.command == "check":
            return check(skills)
    except (SkillError, subprocess.CalledProcessError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    for skill in skills:
        print(f"{skill.name:<34} {skill.maintainer:<12} {skill.license:<10} {skill.source_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
