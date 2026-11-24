"""Import the two upstream templates into ``template/``.

Sources (both MIT, see THIRD_PARTY_NOTICES.md and PROVENANCE.md):

* vstorm-co/full-stack-ai-agent-template: the backend, deployment and agent
  layers. Its cookiecutter files are kept as they are, with two mechanical
  changes so that Copier can render them:
  - the ``cookiecutter.`` prefix is dropped from every Jinja expression;
  - files that contain Jinja get the ``.jinja`` suffix (Copier renders only those).
  Its Next.js frontend is not imported.
* fastapi/full-stack-fastapi-template: the React frontend, copied verbatim.

The upstream post-generation hook becomes ``template/_post_gen.py.jinja`` and
runs as a Copier task.

Keelson changes on top of the import live in the same files, so the script
never writes into a non-empty directory. For a re-sync, import into an empty
scratch directory and merge it into ``template/`` with a three-way diff against
the previous import (see PROVENANCE.md, Re-sync procedure).
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

VSTORM_PROJECT_DIR = Path("template") / "{{cookiecutter.project_slug}}"
VSTORM_HOOK = Path("template") / "hooks" / "post_gen_project.py"
OFFICIAL_FRONTEND = Path("frontend")

# Upstream paths (relative to the generated project root) not imported.
VSTORM_EXCLUDED_TOP_LEVEL = {
    "frontend",  # replaced by the official React frontend
}

JINJA_MARKERS = ("{{", "{%", "{#")

# House style: no emoji or pictographic icons in any file (same rule and range as
# scripts/check_style.py). Known symbols get a plain-text equivalent; any other
# pictograph is dropped.
HOUSE_STYLE_REPLACEMENTS = {
    "\u2705": "OK",  # white heavy check mark
    "\u274c": "ERROR",  # cross mark
    "\u25b6": "->",  # play button
    "\u26a0\ufe0f": "WARNING:",
    "\u26a0": "WARNING:",
    "\u2713": "OK",  # check mark
    "\u2717": "FAILED",  # ballot x
    "\U0001f527": "Tool:",  # wrench
    "\U0001f44d": "thumbs up",
    "\U0001f44e": "thumbs down",
}
_PICTOGRAPH = "[\U0001f000-\U0001faff\u2600-\u27bf\u25a0-\u25ff\u2b00-\u2bff\ufe0f]+"
PICTOGRAPH_AT_END = re.compile(r"[ \t]*" + _PICTOGRAPH + r"[ \t]*(?=[\"'<\n]|$)", re.MULTILINE)
PICTOGRAPH_INLINE = re.compile(_PICTOGRAPH + r"[ \t]*")
POST_GEN_NAME = "_post_gen.py.jinja"


def _is_text(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _house_style(text: str) -> str:
    for symbol, plain in HOUSE_STYLE_REPLACEMENTS.items():
        text = text.replace(symbol, plain)
    # A pictograph at the end of a phrase takes the space before it; elsewhere the space after it.
    text = PICTOGRAPH_AT_END.sub("", text)
    return PICTOGRAPH_INLINE.sub("", text)


def _convert_text(text: str) -> str:
    return text.replace("cookiecutter.", "")


def import_vstorm(vstorm_root: Path, dest: Path) -> int:
    src_root = vstorm_root / VSTORM_PROJECT_DIR
    if not src_root.is_dir():
        raise FileNotFoundError(src_root)
    count = 0
    for src in sorted(src_root.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(src_root)
        if rel.parts[0] in VSTORM_EXCLUDED_TOP_LEVEL:
            continue
        target = dest / Path(_convert_text(str(rel)))
        target.parent.mkdir(parents=True, exist_ok=True)
        if _is_text(src):
            text = src.read_text(encoding="utf-8")
            converted = _house_style(_convert_text(text))
            if any(marker in converted for marker in JINJA_MARKERS):
                target = target.with_name(target.name + ".jinja")
            target.write_text(converted, encoding="utf-8")
        else:
            shutil.copyfile(src, target)
        shutil.copymode(src, target)
        count += 1
    hook = vstorm_root / VSTORM_HOOK
    hook_text = _house_style(_convert_text(hook.read_text(encoding="utf-8")))
    (dest / POST_GEN_NAME).write_text(hook_text, encoding="utf-8")
    return count


def import_official_frontend(official_root: Path, dest: Path) -> int:
    src_root = official_root / OFFICIAL_FRONTEND
    target_root = dest / "frontend"
    count = 0
    for src in sorted(src_root.rglob("*")):
        if not src.is_file() or "node_modules" in src.parts:
            continue
        target = target_root / src.relative_to(src_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if _is_text(src):
            target.write_text(_house_style(src.read_text(encoding="utf-8")), encoding="utf-8")
            shutil.copymode(src, target)
        else:
            shutil.copy2(src, target)
        count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--vstorm", type=Path, required=True, help="clone of vstorm-co/full-stack-ai-agent-template"
    )
    parser.add_argument(
        "--official", type=Path, required=True, help="clone of fastapi/full-stack-fastapi-template"
    )
    parser.add_argument("--dest", type=Path, required=True, help="empty directory to import into")
    args = parser.parse_args(argv)

    if args.dest.exists() and any(args.dest.iterdir()):
        print(f"{args.dest} is not empty; import into an empty directory", file=sys.stderr)
        return 1
    args.dest.mkdir(parents=True, exist_ok=True)

    n_backend = import_vstorm(args.vstorm, args.dest)
    n_frontend = import_official_frontend(args.official, args.dest)
    print(f"imported {n_backend} files from vstorm, {n_frontend} from the official frontend")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
