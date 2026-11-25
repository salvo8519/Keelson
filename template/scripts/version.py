"""The project's version: one file, VERSION, and the manifests that must carry it (Keelstone).

VERSION at the root of the project is the only place to change the version. The backend and
the frontend are built from their own folders (each Docker build sees only its folder), so
their manifests keep a copy, written by this script and checked by ``make lint``:

    python3 scripts/version.py show
    python3 scripts/version.py bump patch|minor|major
    python3 scripts/version.py set 1.4.0
    python3 scripts/version.py check

The backend reads its version from the installed package (OpenAPI document, logs); the
frontend from its package.json at build time (shown at the bottom of the sidebar).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
BACKEND = ROOT / "backend" / "pyproject.toml"
FRONTEND = ROOT / "frontend" / "package.json"

SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
# The version line of the [project] table: the first top-level `version = "..."`.
PYPROJECT_VERSION = re.compile(r'^version = "([^"]*)"$', re.MULTILINE)
PARTS = ("major", "minor", "patch")


def fail(message: str) -> NoReturn:
    raise SystemExit(message)


def read() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not SEMVER.fullmatch(version):
        fail(f"VERSION must be MAJOR.MINOR.PATCH, found {version!r}")
    return version


def bumped(version: str, part: str) -> str:
    major, minor, patch = (int(n) for n in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def manifests() -> dict[str, str | None]:
    """The version each manifest carries, or None when the manifest is absent."""
    found: dict[str, str | None] = {}
    if BACKEND.exists():
        match = PYPROJECT_VERSION.search(BACKEND.read_text(encoding="utf-8"))
        found[str(BACKEND.relative_to(ROOT))] = match.group(1) if match else ""
    if FRONTEND.exists():
        package = json.loads(FRONTEND.read_text(encoding="utf-8"))
        found[str(FRONTEND.relative_to(ROOT))] = package.get("version", "")
    return found


def write(version: str) -> None:
    if not SEMVER.fullmatch(version):
        fail(f"not a MAJOR.MINOR.PATCH version: {version!r}")
    VERSION_FILE.write_text(version + "\n", encoding="utf-8")
    if BACKEND.exists():
        text = BACKEND.read_text(encoding="utf-8")
        if not PYPROJECT_VERSION.search(text):
            fail(f"no version line in {BACKEND}")
        text = PYPROJECT_VERSION.sub(f'version = "{version}"', text, count=1)
        BACKEND.write_text(text, encoding="utf-8")
    if FRONTEND.exists():
        package = json.loads(FRONTEND.read_text(encoding="utf-8"))
        package["version"] = version
        text = json.dumps(package, indent=2, ensure_ascii=False) + "\n"
        FRONTEND.write_text(text, encoding="utf-8")


def check() -> list[str]:
    """Manifests whose version differs from VERSION."""
    version = read()
    return [
        f"{path}: {found!r}, VERSION: {version!r}"
        for path, found in manifests().items()
        if found != version
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("show", help="print the version")
    bump = commands.add_parser("bump", help="raise one part of the version")
    bump.add_argument("part", choices=PARTS)
    exact = commands.add_parser("set", help="set an exact version")
    exact.add_argument("version")
    commands.add_parser("check", help="fail when a manifest differs from VERSION")
    args = parser.parse_args(argv)

    if args.command == "show":
        print(read())
    elif args.command == "bump":
        new = bumped(read(), args.part)
        write(new)
        print(new)
    elif args.command == "set":
        write(args.version)
        print(args.version)
    else:
        problems = check()
        for problem in problems:
            print(problem, file=sys.stderr)
        if problems:
            print("run: python3 scripts/version.py set $(cat VERSION)", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
