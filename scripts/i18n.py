"""Keelson runs the documentation tool of generated projects (template/scripts/i18n.py) on its
own repository, so there is one copy of it. Same commands: see that file."""

import os
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DOCS_ROOT", str(ROOT))
runpy.run_path(str(ROOT / "template" / "scripts" / "i18n.py"), run_name="__main__")
