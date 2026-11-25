"""Track translations of the documentation and root documents against their English source.

Every translated file starts with front matter naming its source and the hash of the source
it was translated from:

    ---
    source: getting-started/quickstart.md
    source_hash: 3f9a1c0b7d2e
    ---

    uv run python scripts/i18n.py status            # table: translated, stale, missing
    uv run python scripts/i18n.py check             # fail on stale/missing required pages
    uv run python scripts/i18n.py stamp docs/it/getting-started/quickstart.md
                                                    # after (re)translating a page
    uv run python scripts/i18n.py todo              # stale and missing pages, one per line

Translations of root documents (README.<lang>.md), and pages that other sites include as
snippets, carry the same data in an HTML comment on the first line, because front matter would
be rendered as text there:

    <!-- i18n source: README.md source_hash: 3f9a1c0b7d2e -->
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# One copy serves Keelstone and every generated project: DOCS_ROOT selects the repository.
ROOT = Path(os.environ.get("DOCS_ROOT") or Path(__file__).resolve().parents[1]).resolve()
EN = ROOT / "docs" / "en"
FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
COMMENT = re.compile(r"\A<!-- i18n source: (\S+) source_hash: (\S+) -->\n")


# Generated blocks (README methods table) are produced in every language by the generator,
# so they do not make a translation stale.
GENERATED = re.compile(rb"<!-- generated:[a-z]+:start.*?<!-- generated:[a-z]+:end -->", re.DOTALL)


def digest(path: Path) -> str:
    return hashlib.sha256(GENERATED.sub(b"", path.read_bytes())).hexdigest()[:12]


def meta(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    c = COMMENT.match(text)
    if c:
        return {"source": c.group(1), "source_hash": c.group(2)}
    m = FRONT.match(text)
    data = yaml.safe_load(m.group(1)) if m else {}
    return data if isinstance(data, dict) else {}


def languages() -> dict[str, dict[str, Any]]:
    return {
        p.stem: yaml.safe_load(p.read_text(encoding="utf-8"))
        for p in sorted((ROOT / "i18n").glob("*.yaml"))
        if p.stem != "glossary"
    }


def pairs(lang: str, cfg: dict[str, Any]) -> list[tuple[str, Path, Path, bool]]:
    """(name, source, translation, required) for every page that should be translated."""
    out = []
    for src in sorted(EN.rglob("*.md")):
        rel = src.relative_to(EN).as_posix()
        if any(
            fnmatch.fnmatch(rel, p) for p in cfg.get("english_only", []) + cfg.get("generated", [])
        ):
            continue
        required = any(fnmatch.fnmatch(rel, p) for p in cfg.get("required", []))
        out.append((rel, src, ROOT / "docs" / lang / rel, required))
    # Documents at the repository root translated as <NAME>.<lang>.md (``root_documents``).
    for name in cfg.get("root_documents", []):
        stem = name.removesuffix(".md")
        out.append((name, ROOT / name, ROOT / f"{stem}.{lang}.md", True))
    return out


def evaluate() -> list[tuple[str, str, str, bool]]:
    rows = []
    for lang, cfg in languages().items():
        for rel, src, dst, required in pairs(lang, cfg):
            if not dst.exists():
                state = "missing"
            elif meta(dst).get("source_hash") != digest(src):
                state = "stale"
            else:
                state = "translated"
            rows.append((lang, rel, state, required))
    return rows


def stamp(path: Path) -> None:
    path = path.resolve()
    text = path.read_text(encoding="utf-8")
    root_documents = {n for cfg in languages().values() for n in cfg.get("root_documents", [])}
    if path.parent == ROOT and path.name in root_documents:
        sys.exit(f"{path.name} is an English source: stamp its translation instead.")
    root_source = next(
        (
            n
            for n in sorted(root_documents)
            if path.parent == ROOT and re.fullmatch(rf"{n[:-3]}\.[a-z]{{2}}\.md", path.name)
        ),
        None,
    )
    if root_source:
        body = COMMENT.sub("", text, count=1)
        line = f"<!-- i18n source: {root_source} source_hash: {digest(ROOT / root_source)} -->\n"
        path.write_text(line + body, encoding="utf-8")
        print(f"Stamped {path.relative_to(ROOT)} against {root_source}.")
        return
    else:
        lang = path.relative_to(ROOT / "docs").parts[0]
        rel = path.relative_to(ROOT / "docs" / lang).as_posix()
        src = EN / rel
    if COMMENT.match(text):
        # Pages included in another site (snippets) keep the comment form: front matter would
        # show as text where they are included.
        body = COMMENT.sub("", text, count=1)
        path.write_text(
            f"<!-- i18n source: {rel} source_hash: {digest(src)} -->\n" + body, encoding="utf-8"
        )
        print(f"Stamped {path.relative_to(ROOT)} against {rel} ({digest(src)}).")
        return
    data = meta(path)
    body = FRONT.sub("", text, count=1)
    data.update({"source": rel, "source_hash": digest(src)})
    path.write_text(
        "---\n"
        + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        + "---\n"
        + body.lstrip("\n"),
        encoding="utf-8",
    )
    print(f"Stamped {path.relative_to(ROOT)} against {rel} ({data['source_hash']}).")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "check", "stamp", "todo"])
    parser.add_argument("files", nargs="*", type=Path)
    args = parser.parse_args()

    if args.command == "stamp":
        for f in args.files:
            stamp(f)
        return
    rows = evaluate()
    if args.command == "todo":
        for lang, rel, state, _ in rows:
            if state != "translated":
                print(f"{lang}\t{state}\t{rel}")
        return
    if args.command == "status":
        for lang, rel, state, required in rows:
            print(f"{lang}  {state:<10} {'required' if required else 'optional':<8}  {rel}")
        done = sum(r[2] == "translated" for r in rows)
        print(f"\n{done}/{len(rows)} pages translated and current.")
        return
    problems = [r for r in rows if r[3] and r[2] != "translated"]
    if problems:
        print("Translations out of date or missing (English is the source):")
        for lang, rel, state, _ in problems:
            print(f"  {lang}: {state:<8} {rel}")
        print("Translate, then stamp: python scripts/i18n.py stamp <file>")
        sys.exit(1)
    print("All required translations are current.")


if __name__ == "__main__":
    main()
