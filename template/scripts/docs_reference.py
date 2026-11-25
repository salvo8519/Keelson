"""Reference pages generated from the code at every documentation build (Keelstone).

    cd backend && uv run python ../scripts/docs_reference.py   (make docs runs it)

Writes .generated/docs/<lang>/reference/api.md (every endpoint, from the OpenAPI schema) and
settings.md (every setting of app.core.config.Settings, with its type and default), for
English and each edition in i18n/. The pages in docs/<lang>/reference include them, so the
site always matches the code and the strict build fails when they are missing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic_core import PydanticUndefined

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".generated" / "docs"
METHODS = ("get", "post", "put", "patch", "delete")
# Defaults of these settings are development placeholders or secrets: not published.
SENSITIVE = re.compile(r"SECRET|PASSWORD|TOKEN|API_KEY|DSN|CREDENTIAL|PRIVATE", re.IGNORECASE)

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "method": "Method",
        "path": "Path",
        "summary": "Summary",
        "setting": "Setting",
        "type": "Type",
        "default": "Default",
        "secret": "set in the environment",
        "none": "none",
        "untagged": "Other",
    },
    "it": {
        "method": "Metodo",
        "path": "Percorso",
        "summary": "Descrizione",
        "setting": "Impostazione",
        "type": "Tipo",
        "default": "Predefinito",
        "secret": "da impostare nell'ambiente",
        "none": "nessuno",
        "untagged": "Altro",
    },
}


def languages() -> list[str]:
    editions = sorted(p.stem for p in (ROOT / "i18n").glob("*.yaml") if p.stem != "glossary")
    return ["en", *editions]


def cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def api_page(schema: dict[str, Any], labels: dict[str, str]) -> str:
    groups: dict[str, list[tuple[str, str, str]]] = {}
    for path, operations in schema.get("paths", {}).items():
        for method in METHODS:
            operation = operations.get(method)
            if operation is None:
                continue
            tag = (operation.get("tags") or [labels["untagged"]])[0]
            summary = operation.get("summary") or operation.get("operationId", "")
            groups.setdefault(tag, []).append((method.upper(), path, summary))
    declared = [t["name"] for t in schema.get("tags", []) if t["name"] in groups]
    order = declared + sorted(t for t in groups if t not in declared)
    lines: list[str] = []
    for tag in order:
        lines += [
            f"## {tag}",
            "",
            f"| {labels['method']} | {labels['path']} | {labels['summary']} |",
            "| --- | --- | --- |",
        ]
        lines += [f"| {m} | `{cell(p)}` | {cell(s)} |" for m, p, s in groups[tag]]
        lines.append("")
    return "\n".join(lines)


def type_name(annotation: object) -> str:
    text = getattr(annotation, "__name__", None) if isinstance(annotation, type) else None
    text = text or str(annotation)
    return re.sub(r"\b(typing|pathlib|pydantic\.[a-z_.]+)\.", "", text).replace("NoneType", "None")


def settings_page(settings_class: Any, labels: dict[str, str]) -> str:
    lines = [
        f"| {labels['setting']} | {labels['type']} | {labels['default']} |",
        "| --- | --- | --- |",
    ]
    for name, field in settings_class.model_fields.items():
        if field.default is not PydanticUndefined:
            default = field.default
        elif field.default_factory is not None and not field.default_factory_takes_data:
            default = field.default_factory()
        else:
            default = None
        if SENSITIVE.search(name) and default not in (None, "", [], {}):
            shown = f"*{labels['secret']}*"
        elif default in (None, "", [], {}):
            shown = labels["none"]
        else:
            shown = f"`{cell(default)}`"
        lines.append(f"| `{name}` | `{cell(type_name(field.annotation))}` | {shown} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    # The same document as openapi/openapi.json: built from the defaults, without a .env.
    from openapi import build

    schema = build()
    # The backend of the generated project, on the path once build() has loaded it.
    from app.core.config import Settings  # type: ignore[import-not-found]

    for lang in languages():
        labels = LABELS.get(lang, LABELS["en"])
        target = OUT / lang / "reference"
        target.mkdir(parents=True, exist_ok=True)
        (target / "api.md").write_text(api_page(schema, labels), encoding="utf-8")
        (target / "settings.md").write_text(settings_page(Settings, labels), encoding="utf-8")
    print(f"Reference pages written to {OUT.relative_to(ROOT)} for {', '.join(languages())}.")


if __name__ == "__main__":
    main()
