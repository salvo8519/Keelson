"""The published OpenAPI document carries no internal notes (Keelstone).

Route docstrings become operation descriptions. Notes for maintainers (why a route runs as
the system, which upstream behaviour changed, file paths) go after a form feed (``\\f``),
where FastAPI stops reading, so clients see only what the endpoint does.
"""

import re
from typing import Any

from app.main import app

INTERNAL = re.compile(r"Keelstone|Upstream|upstream|app/[a-z_/]+\.py|\.py\b")


def _texts(document: dict[str, Any]) -> list[tuple[str, str]]:
    found = []
    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            for key in ("summary", "description"):
                text = operation.get(key) or ""
                found.append((f"{method.upper()} {path} {key}", text))
    return found


def test_operation_descriptions_carry_no_internal_notes() -> None:
    leaks = [where for where, text in _texts(app.openapi()) if INTERNAL.search(text)]
    assert leaks == [], f"internal notes in the API reference: {leaks}"
