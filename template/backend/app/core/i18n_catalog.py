"""Extraction and coverage of the message catalogs (Keelstone).

The messages of the API are the string arguments of the application exceptions
(``raise NotFoundError(message="...")``) and of ``N_()``. This module extracts them with Babel
and compares them with the catalogs, so a message without a translation is caught by a test
instead of reaching a user in English.

    uv run python -m app.core.i18n_catalog extract   # write messages.pot, merge into catalogs
    uv run python -m app.core.i18n_catalog check     # exit 1 when a message is untranslated
"""

import argparse
import inspect
import sys
from pathlib import Path

from babel.messages.catalog import Catalog
from babel.messages.extract import extract_from_dir
from babel.messages.pofile import read_po, write_po

from app.core import exceptions
from app.core.i18n import DEFAULT_LANGUAGE, DOMAIN, LOCALES_DIR, SUPPORTED_LANGUAGES

APP_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = LOCALES_DIR / f"{DOMAIN}.pot"


def keywords() -> dict[str, None]:
    """Every application exception, plus N_, extracted like gettext calls."""
    names = {
        name
        for name, cls in inspect.getmembers(exceptions, inspect.isclass)
        if issubclass(cls, exceptions.AppException)
    }
    return dict.fromkeys(sorted(names | {"N_"}))


def extract() -> set[str]:
    messages: set[str] = set()
    for _filename, _lineno, message, _comments, _context in extract_from_dir(
        str(APP_DIR), keywords=keywords(), method_map=[("**.py", "python")]
    ):
        text = message[0] if isinstance(message, tuple) else message
        if text:
            messages.add(text)
    return messages


def _catalog_path(language: str) -> Path:
    return LOCALES_DIR / language / "LC_MESSAGES" / f"{DOMAIN}.po"


def write_template_and_merge(messages: set[str]) -> None:
    template = Catalog(project="api", domain=DOMAIN)
    for message in sorted(messages):
        template.add(message)
    TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    with TEMPLATE.open("wb") as handle:
        write_po(handle, template, omit_header=True, sort_output=True)
    for language in SUPPORTED_LANGUAGES:
        if language == DEFAULT_LANGUAGE:
            continue
        path = _catalog_path(language)
        if path.is_file():
            with path.open("rb") as handle:
                catalog = read_po(handle, locale=language)
        else:
            catalog = Catalog(locale=language, domain=DOMAIN)
        catalog.update(template, no_fuzzy_matching=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            write_po(handle, catalog, omit_header=True, sort_output=True, ignore_obsolete=True)


def untranslated(messages: set[str]) -> dict[str, list[str]]:
    """Messages with no translation, per non-default language."""
    missing: dict[str, list[str]] = {}
    for language in SUPPORTED_LANGUAGES:
        if language == DEFAULT_LANGUAGE:
            continue
        path = _catalog_path(language)
        translated: set[str] = set()
        if path.is_file():
            with path.open("rb") as handle:
                translated = {
                    str(m.id) for m in read_po(handle, locale=language) if m.id and m.string
                }
        gaps = sorted(messages - translated)
        if gaps:
            missing[language] = gaps
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["extract", "check"])
    args = parser.parse_args(argv)
    messages = extract()
    if args.command == "extract":
        write_template_and_merge(messages)
        print(f"{len(messages)} messages extracted")
    missing = untranslated(messages)
    for language, gaps in missing.items():
        print(f"{language}: {len(gaps)} untranslated", file=sys.stderr)
        for gap in gaps:
            print(f"  {gap}", file=sys.stderr)
    return 1 if missing and args.command == "check" else 0


if __name__ == "__main__":
    raise SystemExit(main())
