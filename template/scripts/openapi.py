"""The OpenAPI document of the API, kept in the repository and checked against the code (Keelstone).

    cd backend && uv run python ../scripts/openapi.py export   # write openapi/openapi.json
    cd backend && uv run python ../scripts/openapi.py check    # fail if it differs from the code

openapi/openapi.json is the contract of the API: it is versioned with the code, reviewed in
pull requests, compared with the target branch for breaking changes (oasdiff, in the pipeline),
used to generate the frontend client and published with the documentation site. The document
is built from the application's defaults, not from a local .env, so it is the same on every
machine.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "openapi" / "openapi.json"


def build() -> dict[str, Any]:
    """The OpenAPI document of the application, as FastAPI serves it in development."""
    # Defaults only: settings look for a .env in the working directory and its parent, so work
    # from an empty temporary directory; and an environment where the document is served.
    os.chdir(tempfile.mkdtemp(prefix="openapi-"))
    os.environ["ENVIRONMENT"] = "local"
    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import create_app  # type: ignore[import-not-found]

    document: dict[str, Any] = create_app().openapi()
    return document


def render(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in ("export", "check"):
        print(__doc__)
        return 2
    DOCUMENT.parent.mkdir(exist_ok=True)
    text = render(build())
    relative = DOCUMENT.relative_to(ROOT)
    if command == "export":
        DOCUMENT.write_text(text, encoding="utf-8")
        print(f"Wrote {relative}.")
        return 0
    if not DOCUMENT.exists() or DOCUMENT.read_text(encoding="utf-8") != text:
        print(
            f"{relative} does not match the code. Run "
            "`cd backend && uv run python ../scripts/openapi.py export` and commit the result."
        )
        return 1
    print(f"{relative} matches the code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
