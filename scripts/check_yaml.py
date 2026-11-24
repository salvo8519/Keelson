"""Every YAML file in the repository parses: a broken file must fail CI, not wait for the tool
that happens to read it (a translation glossary went unread for days).

    python scripts/check_yaml.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import _git
import yaml

ROOT = Path(__file__).resolve().parents[1]


class CopierLoader(yaml.SafeLoader):
    """Safe loader that also reads Copier's `!include` tag (copier.yml)."""


def _include(loader: yaml.SafeLoader, node: yaml.Node) -> str:
    target = str(loader.construct_scalar(node))  # type: ignore[arg-type]
    if not (ROOT / target).is_file():
        raise yaml.constructor.ConstructorError(None, None, f"!include {target}: no such file")
    return target


CopierLoader.add_constructor("!include", _include)


def tracked_yaml() -> list[Path]:
    return [ROOT / f for f in _git.ls_files("*.yml", "*.yaml", cwd=ROOT)]


def main() -> None:
    problems = []
    files = tracked_yaml()
    for path in files:
        try:
            list(yaml.load_all(path.read_text(encoding="utf-8"), Loader=CopierLoader))
        except yaml.YAMLError as err:
            problems.append(f"{path.relative_to(ROOT)}: {err}".replace("\n", " "))
    if problems:
        sys.exit("Invalid YAML:\n  " + "\n  ".join(problems))
    print(f"{len(files)} YAML files parse.")


if __name__ == "__main__":
    main()
