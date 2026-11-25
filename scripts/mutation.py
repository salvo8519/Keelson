"""Mutation testing of the security-critical modules of a generated project (mutmut).

A mutant is a copy of a module with one small change (a condition negated, a constant altered,
an argument dropped). The test suite should fail on each of them; a mutant that survives marks
behaviour no test pins down. Too slow for ``just check``: run it after changing these modules.

    python scripts/mutation.py                      # render the defaults, then mutate
    python scripts/mutation.py --project <backend>  # an already rendered backend
    python scripts/mutation.py --project <backend> --summary-only

The configuration is written to ``setup.cfg`` of the rendered backend, mutmut is installed in
its environment only, and the score is printed per module. ``mutmut results`` and
``mutmut show <mutant>`` in the backend list and explain the survivors.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER_DIR = ROOT / ".generated" / "mutation"
MUTMUT = "mutmut==3.8.1"

# Module -> functions in scope (None: every function of the module).
MODULES: dict[str, frozenset[str] | None] = {
    "app/core/oidc.py": None,
    "app/core/workload_identity.py": None,
    "app/core/api_keys.py": None,
    "app/core/crypto.py": None,
    "app/core/logging.py": None,
    "app/core/security.py": frozenset(
        {"verify_password", "verify_and_update_password", "get_password_hash"}
    ),
}
# Fast tests that exercise these modules; none needs PostgreSQL.
TESTS = (
    "tests/test_sso.py",
    "tests/test_workload_identity.py",
    "tests/test_api_keys.py",
    "tests/test_data_encryption.py",
    "tests/test_log_trap.py",
    "tests/test_security.py",
    "tests/test_production_settings.py",
    "tests/test_user_password.py",
    "tests/test_observability.py",
    "tests/test_services.py",
    "tests/api/test_auth.py",
)
# Directories the application imports besides app/.
ALSO_COPY = ("cli", "emails", "alembic", "alembic.ini")

# mutmut's exit codes per mutant: 1 the tests failed (killed), 0 they passed (survived), -24
# the CPU time limit stopped them (timeout: on a loaded machine, run again before reading it).
STATUS = {1: "killed", 0: "survived", -24: "timeout", 33: "no tests", None: "no tests"}


def _lines(key: str, values: list[str] | tuple[str, ...]) -> str:
    return f"{key}=\n" + "".join(f"    {value}\n" for value in values)


def write_config(backend: Path) -> None:
    tests = [test for test in TESTS if (backend / test).is_file()]
    config = (
        "[mutmut]\n"
        "source_paths=app\n"
        + _lines("only_mutate", list(MODULES))
        + _lines("also_copy", [path for path in ALSO_COPY if (backend / path).exists()])
        + _lines("pytest_add_cli_args_test_selection", tests)
        + _lines("pytest_add_cli_args", ["-p", "no:cacheprovider", "-q"])
    )
    (backend / "setup.cfg").write_text(config, encoding="utf-8")


def render() -> Path:
    shutil.rmtree(RENDER_DIR, ignore_errors=True)
    subprocess.run(
        ["copier", "copy", "--trust", "--defaults", "--vcs-ref", "HEAD", ".", str(RENDER_DIR)],
        cwd=ROOT,
        check=True,
    )
    return RENDER_DIR / "backend"


def run(backend: Path, children: int) -> None:
    # The backend's own environment, not the one of the repository's tooling running this.
    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    subprocess.run(["uv", "sync", "-q"], cwd=backend, env=env, check=True)
    install = ["uv", "pip", "install", "-q", "--python", ".venv", MUTMUT]
    subprocess.run(install, cwd=backend, env=env, check=True)
    shutil.rmtree(backend / "mutants", ignore_errors=True)
    write_config(backend)
    command = ["uv", "run", "--no-sync", "mutmut", "run", "--max-children", str(children)]
    subprocess.run(command, cwd=backend, env=env, check=True, stdout=subprocess.DEVNULL)


def _function(key: str) -> str:
    """``app.core.logging.xǁJsonFormatterǁformat__mutmut_3`` -> ``JsonFormatter.format``."""
    name = key.rsplit("__mutmut_", 1)[0].rsplit(".", 1)[-1].removeprefix("x_")
    return ".".join(part for part in name.split("ǁ") if part and part != "x")


def summary(backend: Path) -> int:
    """Print the score per module; the number of surviving mutants is returned."""
    survivors = 0
    for module, functions in MODULES.items():
        meta = backend / "mutants" / f"{module}.meta"
        codes = json.loads(meta.read_text(encoding="utf-8"))["exit_code_by_key"]
        counts: Counter[str] = Counter()
        for key, code in codes.items():
            if functions is None or _function(key) in functions:
                counts[STATUS.get(code, f"exit {code}")] += 1
        total = sum(counts.values())
        score = 100 * counts["killed"] / total if total else 100.0
        scope = "" if functions is None else f" ({', '.join(sorted(functions))})"
        print(f"{module}{scope}: {counts['killed']}/{total} killed, {score:.1f}%, {dict(counts)}")
        survivors += total - counts["killed"]
    return survivors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", type=Path, help="a rendered backend (default: render)")
    parser.add_argument("--summary-only", action="store_true", help="print the last scores")
    parser.add_argument("--max-children", type=int, default=8)
    args = parser.parse_args()
    backend = args.project.resolve() if args.project else None
    if not args.summary_only:
        backend = backend or render()
        run(backend, args.max_children)
    if backend is None:
        sys.exit("--summary-only needs --project")
    summary(backend)


if __name__ == "__main__":
    main()
