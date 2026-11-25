"""Build the Copier computed variables that drive the imported vstorm template.

The upstream Full-Stack AI Agent Template (vstorm-co, MIT) is a cookiecutter
template whose ~200 context variables are derived by its own generator
(``fastapi_gen.config.ProjectConfig``) from a handful of user choices.

Keelson keeps the upstream Jinja files as they are, so instead of rewriting
that derivation by hand we ask the upstream generator for the context of every
valid combination of the Keelson axes, then express each variable as:

* a constant, when it never changes across combinations;
* a Jinja lookup keyed on the smallest set of axes that determines it.

The output is ``copier/vstorm.yml``, included by ``copier.yml``. Re-run this
script whenever the upstream template is re-synced (see PROVENANCE.md).

Usage (needs the upstream generator installed, see CONTRIBUTING.md):

    python scripts/upstream/build_vstorm_context.py --out copier/vstorm.yml
"""

from __future__ import annotations

import argparse
import itertools
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from fastapi_gen.config import ProjectConfig, RAGFeatures

# ---------------------------------------------------------------------------
# Keelson axes: the only choices exposed as Copier questions that change the
# upstream context. Everything else is fixed by FIXED_OPTIONS below.
# ---------------------------------------------------------------------------
AXES: dict[str, list[Any]] = {
    "web_frontend": ["react", "none"],
    "task_backend": ["taskiq", "celery", "arq"],
    "ai_framework": ["pydantic_ai", "langgraph", "langchain", "deepagents", "pydantic_deep"],
    "llm_provider": ["openai", "anthropic", "google", "openrouter", "openai_compatible", "all"],
    "vector_database": ["none", "qdrant", "pgvector"],
    "ci_provider": ["gitlab", "github"],
    "kubernetes": [True, False],
    "logfire": [False, True],
}

# Opinionated Keelson baseline: multi-company, async, observable, deployable.
FIXED_OPTIONS: dict[str, Any] = {
    "database": "postgresql",
    "orm_type": "sqlalchemy",
    "auth_mode": "local",
    "enable_redis": True,
    "enable_caching": True,
    "enable_rate_limiting": True,
    "rate_limit_storage": "redis",
    "enable_websockets": True,
    "enable_teams": True,
    "tenancy": "multi_org",
    "enable_email": True,
    "email_provider": "smtp",
    "enable_prometheus": True,
    "enable_sentry": False,
    "enable_admin_panel": False,
    "reverse_proxy": "traefik_included",
    "python_version": "3.13",
    # Upstream i18n is next-intl only; Keelson ships its own i18n (M3).
    "enable_i18n": False,
    "enable_billing": False,
    "use_telegram": False,
    "use_slack": False,
    # Upstream's S3 settings and boto3; Keelson adds the object store behind them
    # (app/services/file_storage.py, docs/en/concepts/document-storage.md).
    "enable_file_storage": True,
}

# Context keys that come straight from Copier questions, not from this file.
# Keelson question names never collide with upstream keys unless listed here
# as an identical pass-through (checked in build()).
PASSTHROUGH = {
    "project_name",
    "project_slug",
    "project_description",
    "author_name",
    "author_email",
    "timezone",
    "generator_name",
    "generator_version",
    "generated_at",
    # Same name and same values as the Keelson questions: passed through.
    "ai_framework",
    "llm_provider",
}


class ContextError(ValueError):
    """The upstream context cannot be expressed as Copier variables."""

    def __init__(self, key: str, problem: str) -> None:
        super().__init__(f"{key}: {problem}")


# Sentinel project values used only to build configs; never emitted.
_PLACEHOLDER_NAME = "keelson_probe"


def _to_config_kwargs(axis_values: dict[str, Any]) -> dict[str, Any]:
    vector_store = axis_values["vector_database"]
    rag = RAGFeatures(
        enable_rag=vector_store != "none",
        vector_store=vector_store if vector_store != "none" else "qdrant",
    )
    return {
        **FIXED_OPTIONS,
        "project_name": _PLACEHOLDER_NAME,
        # Upstream renders backend wiring for a frontend only when one exists;
        # Keelson replaces the upstream Next.js app with the official React one.
        "frontend": "nextjs" if axis_values["web_frontend"] == "react" else "none",
        "background_tasks": axis_values["task_backend"],
        "ai_framework": axis_values["ai_framework"],
        "llm_provider": axis_values["llm_provider"],
        "rag_features": rag,
        "ci_type": axis_values["ci_provider"],
        "enable_kubernetes": axis_values["kubernetes"],
        "enable_logfire": axis_values["logfire"],
        # Upstream's OAuth sign-in (Authlib, identities on the user, the session middleware)
        # needs a frontend for its callback. Keelson generalises it to any OpenID Connect
        # provider configured at run time (app/core/oauth.py); Google is one of them.
        "oauth_provider": "google" if axis_values["web_frontend"] == "react" else "none",
    }


def _valid_contexts() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    names = list(AXES)
    results: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for combo in itertools.product(*AXES.values()):
        axis_values = dict(zip(names, combo, strict=True))
        try:
            config = ProjectConfig(**_to_config_kwargs(axis_values))
        except ValueError:
            continue  # invalid upstream combination, rejected by copier.yml validators
        results.append((axis_values, config.to_cookiecutter_context()))
    return results


def _determined_by(
    key: str, subset: tuple[str, ...], rows: list[tuple[dict[str, Any], dict[str, Any]]]
) -> bool:
    seen: dict[tuple[Any, ...], Any] = {}
    for axis_values, ctx in rows:
        k = tuple(axis_values[a] for a in subset)
        if k in seen and seen[k] != ctx[key]:
            return False
        seen[k] = ctx[key]
    return True


def _minimal_axes(key: str, rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> tuple[str, ...]:
    names = list(AXES)
    for size in range(len(names) + 1):
        for subset in itertools.combinations(names, size):
            if _determined_by(key, subset, rows):
                return subset
    raise ContextError(key, "not determined by the axes")  # pragma: no cover


def _jinja_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    raise ContextError(repr(value), "unsupported context value")


def _copier_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def _axis_key_expr(subset: Iterable[str]) -> str:
    parts = [f"({a} | string)" for a in subset]
    return " ~ '|' ~ ".join(parts)


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def build(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    for axis in AXES:
        if axis in rows[0][1] and axis not in PASSTHROUGH:
            raise ContextError(axis, "Keelson question collides with an upstream key")
    for axis_values, ctx in rows:
        for key in PASSTHROUGH & set(AXES):
            if ctx[key] != axis_values[key]:
                raise ContextError(key, "is not an identity pass-through")
    keys = sorted(k for k in rows[0][1] if k not in PASSTHROUGH)
    lines = [
        "# Generated by scripts/upstream/build_vstorm_context.py. Do not edit by hand.",
        "# Computed variables consumed by the Jinja files imported from the upstream",
        "# Full-Stack AI Agent Template (vstorm-co, MIT). See PROVENANCE.md.",
        "",
    ]
    for key in keys:
        sample = rows[0][1][key]
        if isinstance(sample, (list, dict)) or sample is None:
            raise ContextError(key, f"unsupported context type {type(sample).__name__}")
        subset = _minimal_axes(key, rows)
        lines.append(f"{key}:")
        lines.append(f"  type: {_copier_type(sample)}")
        lines.append("  when: false")
        if not subset:
            lines.append(f"  default: {_yaml_scalar(sample)}")
        else:
            table: dict[str, Any] = {}
            for axis_values, ctx in rows:
                table["|".join(str(axis_values[a]) for a in subset)] = ctx[key]
            entries = ", ".join(
                f"{_jinja_literal(k)}: {_jinja_literal(v)}" for k, v in sorted(table.items())
            )
            expr = "{{ {" + entries + "}[" + _axis_key_expr(subset) + "] }}"
            lines.append("  default: " + _yaml_scalar(expr))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    rows = _valid_contexts()
    if not rows:
        print("no valid combination", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(rows), encoding="utf-8")
    print(f"{len(rows)} valid combinations -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
