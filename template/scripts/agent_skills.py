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
    python scripts/agent_skills.py scan             # scan the installed skills (exit 1 on a block)
    python scripts/agent_skills.py digest           # content digests, to pin in the lock file

Supply chain (Keelstone). A skill is text that an agent follows, so it is checked like code:

* a git source is pinned to a commit and, with ``sha256``, to the digest of its content: a
  different content (a rewritten tag, a compromised mirror, a tampered cache) is refused;
* every skill, package sources included, is scanned before it is installed. ``block`` findings
  stop the install: hidden Unicode (text an agent reads but a reviewer does not see),
  instructions to override the agent's rules, piping a download into a shell, reading
  credential files. ``warn`` findings are printed: scripts and binaries in the skill, commands
  that run the latest version of a package from the network, links to other domains. A block
  finding that a maintainer has reviewed is accepted with ``allow = ["<rule>"]`` in the lock.

Standard library only, so it runs before the project environment exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path.cwd()
TARGETS = (Path(".agents") / "skills", Path(".claude") / "skills")
MARKER = ".skill-source.json"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "agent-skills"
# Keelstone: what a lock entry may contain. The name becomes a folder under TARGETS and the path
# a sparse checkout pattern, so neither may climb out of its place; a package source runs an
# interpreter, so only this one or the project's backend environment.
NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]*")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
PACKAGE_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*")
BACKEND_PYTHON = "backend/.venv/bin/python"


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
    sha256: str | None = None
    allow: tuple[str, ...] = field(default_factory=tuple)

    @property
    def source_id(self) -> str:
        if self.repository:
            return f"{self.repository}@{self.commit}:{self.path}"
        return f"package:{self.package}:{self.path}"


def _validate(skill: Skill) -> None:
    """Refuse a lock entry that could write, fetch or run outside what it declares (Keelstone)."""
    if not NAME_PATTERN.fullmatch(skill.name):
        raise SkillError(repr(skill.name), "a name is lower case letters, digits and hyphens")
    parts = skill.path.split("/")
    if (
        not skill.path
        or skill.path.startswith("/")
        or "\\" in skill.path
        or ":" in skill.path
        or ".." in parts
    ):
        raise SkillError(skill.name, f"path {skill.path!r} must be relative, without '..'")
    if bool(skill.repository) == bool(skill.package):
        raise SkillError(skill.name, "declare either repository+commit or package")
    if skill.repository:
        if not skill.repository.startswith("https://"):
            raise SkillError(skill.name, "a git source is fetched over https:// only")
        if not (skill.commit and COMMIT_PATTERN.fullmatch(skill.commit)):
            raise SkillError(skill.name, "a git source needs a pinned commit (40 hex digits)")
        if not (skill.sha256 and SHA256_PATTERN.fullmatch(skill.sha256)):
            raise SkillError(skill.name, "a git source needs the sha256 of its content")
        if skill.python:
            raise SkillError(skill.name, "python applies to package sources only")
    if skill.package:
        if not PACKAGE_PATTERN.fullmatch(skill.package):
            raise SkillError(skill.name, f"package {skill.package!r} is not a module name")
        if skill.python not in (None, sys.executable, BACKEND_PYTHON):
            allowed = f"{BACKEND_PYTHON} or this interpreter"
            raise SkillError(skill.name, f"python must be {allowed}, not {skill.python!r}")


def load(lock: Path) -> list[Skill]:
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    skills = []
    for entry in data.get("skill", []):
        try:
            skill = Skill(**{**entry, "allow": tuple(entry.get("allow", ()))})
        except TypeError as err:
            raise SkillError(str(lock), f"unexpected or missing field in a skill: {err}") from None
        if not all(isinstance(value, str) for key, value in entry.items() if key != "allow"):
            raise SkillError(str(entry.get("name")), "every field but allow is a string")
        _validate(skill)
        skills.append(skill)
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
    """SHA-256 of a skill folder: relative paths and contents, in a stable order."""
    h = hashlib.sha256()
    files = (p for p in folder.rglob("*") if p.is_file() and p.name not in (MARKER, ".gitignore"))
    for file in sorted(files):
        h.update(file.relative_to(folder).as_posix().encode())
        h.update(b"\0")
        h.update(file.read_bytes())
    return h.hexdigest()


# --- Content scan (Keelstone) -------------------------------------------------------------------

BLOCK = "block"
WARN = "warn"
# (rule, severity, pattern). Patterns run on every line of every text file of the skill.
RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "hidden-unicode",
        BLOCK,
        re.compile(
            "[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]"
        ),
    ),
    (
        "instruction-override",
        BLOCK,
        re.compile(
            r"(ignore|disregard|forget) (all |any )?(the )?(previous|prior|above|system) "
            r"(instructions|rules|prompt)|do not (tell|inform|show) the user",
            re.IGNORECASE,
        ),
    ),
    ("pipe-to-shell", BLOCK, re.compile(r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z)?sh\b")),
    (
        "credential-access",
        BLOCK,
        re.compile(r"(~|\$HOME)/\.(ssh|aws|gnupg|netrc|docker/config)|\bid_(rsa|ed25519)\b"),
    ),
    ("encoded-payload", BLOCK, re.compile(r"base64\s+(-d|--decode)[^\n]*\|\s*(ba)?sh\b")),
    (
        "unpinned-execution",
        WARN,
        re.compile(r"\b(npx|bunx|pnpm dlx|uvx|pipx run)\s+[^\s]+@latest\b"),
    ),
    ("external-link", WARN, re.compile(r"https?://[^\s)>\]\"']+")),
)
SCRIPT_SUFFIXES = {".sh", ".bash", ".zsh", ".py", ".js", ".mjs", ".ts", ".ps1", ".bat", ".cmd"}


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    where: str
    excerpt: str

    def __str__(self) -> str:
        return f"{self.severity:<5} {self.rule:<21} {self.where}  {self.excerpt}"


def scan(folder: Path) -> list[Finding]:
    """Findings in a skill folder; links to the skill's own repository are not reported."""
    findings: list[Finding] = []
    for file in sorted(p for p in folder.rglob("*") if p.is_file()):
        if file.name in (MARKER, ".gitignore"):
            continue
        where = file.relative_to(folder).as_posix()
        if file.suffix.lower() in SCRIPT_SUFFIXES or os.access(file, os.X_OK):
            findings.append(Finding("script", WARN, where, "runs code when an agent follows it"))
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(Finding("binary", WARN, where, "not text: cannot be reviewed"))
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for rule, severity, pattern in RULES:
                match = pattern.search(line)
                if match:
                    shown = match.group(0).encode("unicode_escape").decode()[:80]
                    findings.append(Finding(rule, severity, f"{where}:{number}", shown))
    return findings


def blocking(skill: Skill, findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == BLOCK and f.rule not in skill.allow]


def _verified_source(skill: Skill) -> Path:
    """The skill's source, checked against its pinned digest and scanned."""
    source = _from_git(skill) if skill.repository else _from_package(skill)
    # Keelstone: a link would be copied as the file it points to (copytree follows links), so a
    # skill could bring any file of this machine into the project; links are refused.
    links = sorted(p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_symlink())
    if links:
        raise SkillError(skill.name, f"symbolic links are not accepted: {', '.join(links)}")
    if skill.sha256 and _digest(source) != skill.sha256:
        raise SkillError(
            skill.name, f"content does not match the sha256 in the lock ({skill.source_id})"
        )
    findings = scan(source)
    refused = blocking(skill, findings)
    if refused:
        report = "\n".join(f"    {f}" for f in refused)
        raise SkillError(skill.name, f"refused by the content scan:\n{report}")
    summary = _summary(f for f in findings if f.rule != "external-link")
    if summary:
        print(f"  {skill.name}: {summary}")
    for finding in findings:
        if finding.rule == "unpinned-execution":
            print(
                f"  {skill.name}: runs the latest release of a package from the network when "
                f"an agent follows it, review before use: {finding.where}  {finding.excerpt}"
            )
    return source


def _summary(findings: Iterable[Finding]) -> str:
    counts: dict[str, int] = {}
    for finding in findings:
        key = f"{finding.severity} {finding.rule}"
        counts[key] = counts.get(key, 0) + 1
    return ", ".join(f"{key} x{count}" for key, count in sorted(counts.items()))


def install(skills: list[Skill]) -> None:
    for skill in skills:
        source = _verified_source(skill)
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


def scan_installed(skills: list[Skill]) -> int:
    """Scan what is installed now: findings of every skill, exit 1 on a blocking one."""
    refused = 0
    for skill in skills:
        target = ROOT / TARGETS[0] / skill.name
        if not target.is_dir():
            print(f"{skill.name}: not installed")
            refused += 1
            continue
        findings = scan(target)
        blocked = blocking(skill, findings)
        refused += bool(blocked)
        status = "REFUSED" if blocked else "ok"
        print(f"{skill.name:<34} {status:<8} {_summary(findings) or 'no findings'}")
        shown: set[str] = set()
        for finding in findings:
            # Every blocking finding; the first of each warning, with where to look.
            first = finding.rule not in shown and finding.rule != "external-link"
            if finding in blocked or first:
                print(f"    {finding}")
                shown.add(finding.rule)
    return 1 if refused else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["install", "check", "list", "scan", "digest"])
    parser.add_argument("--lock", type=Path, default=Path("skills.lock.toml"))
    args = parser.parse_args(argv)
    try:
        skills = load(args.lock)
        if args.command == "install":
            install(skills)
            return 0
        if args.command == "check":
            return check(skills)
        if args.command == "scan":
            return scan_installed(skills)
        if args.command == "digest":
            for skill in skills:
                source = _from_git(skill) if skill.repository else _from_package(skill)
                print(f"{skill.name:<34} {_digest(source)}")
            return 0
    except (SkillError, subprocess.CalledProcessError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    for skill in skills:
        print(f"{skill.name:<34} {skill.maintainer:<12} {skill.license:<10} {skill.source_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
