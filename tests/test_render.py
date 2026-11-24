"""Render tests of the template over a matrix of answers.

Each case renders the template with Copier and checks properties that every generated project
must have, plus the files each answer adds or removes.
"""

from __future__ import annotations

import py_compile
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from check_style import FORBIDDEN
from conftest import Render

from copier import run_copy

pytestmark = pytest.mark.render

CASES: dict[str, dict[str, Any]] = {
    "defaults": {},
    "api-only-celery-langgraph": {
        "web_frontend": "none",
        "task_backend": "celery",
        "ai_framework": "langgraph",
        "llm_provider": "anthropic",
        "vector_database": "pgvector",
        "ci_provider": "github",
        "kubernetes": False,
    },
    "arq-on-premise-llm": {
        "task_backend": "arq",
        "llm_provider": "openai_compatible",
        "vector_database": "none",
        "logfire": True,
    },
}

TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".json", ".ts", ".tsx", ".html", ".txt"}


def answers(case: str) -> dict[str, Any]:
    return {"project_name": "acme_service", **CASES[case]}


def text_files(project: Path) -> list[Path]:
    skipped = {"node_modules", ".venv", ".ruff_cache"}
    return [
        p
        for p in project.rglob("*")
        if p.is_file() and p.suffix in TEXT_SUFFIXES and not skipped & set(p.parts)
    ]


@pytest.mark.parametrize("case", list(CASES))
def test_every_project_is_complete_and_clean(render: Render, case: str) -> None:
    project = render(answers(case))
    assert not (project / "_post_gen.py").exists(), "the post-generation task must clean up"
    assert not list(project.rglob("*.jinja")), "no template suffix may reach the project"
    for name in ("NOTICE", "THIRD_PARTY_NOTICES.md", "skills.lock.toml", "AGENTS.md"):
        assert (project / name).is_file(), name
    recorded = yaml.safe_load((project / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert recorded["_src_path"], "the answers file records the template source"
    assert "Keelson" in (project / "NOTICE").read_text(encoding="utf-8")


@pytest.mark.parametrize("case", list(CASES))
def test_python_compiles(render: Render, case: str) -> None:
    project = render(answers(case))
    for path in (project / "backend").rglob("*.py"):
        if ".venv" not in path.parts:
            py_compile.compile(str(path), doraise=True)


@pytest.mark.parametrize("case", list(CASES))
def test_house_style(render: Render, case: str) -> None:
    project = render(answers(case))
    offending = [
        f"{p.relative_to(project)}: {m.group()!r}"
        for p in text_files(project)
        for m in [FORBIDDEN.search(p.read_text(encoding="utf-8", errors="replace"))]
        if m
    ]
    assert not offending


@pytest.mark.parametrize("case", list(CASES))
def test_frontend_follows_the_answer(render: Render, case: str) -> None:
    project = render(answers(case))
    wanted = CASES[case].get("web_frontend", "react") == "react"
    assert (project / "frontend" / "package.json").is_file() is wanted


@pytest.mark.parametrize(
    ("case", "present", "absent"),
    [
        ("defaults", ["taskiq_app.py", "taskiq_worker.py"], ["celery_app.py", "arq_app.py"]),
        ("api-only-celery-langgraph", ["celery_app.py"], ["taskiq_app.py", "taskiq_worker.py"]),
        ("arq-on-premise-llm", ["arq_app.py"], ["taskiq_app.py", "celery_app.py"]),
    ],
)
def test_task_backend_files(
    render: Render, case: str, present: list[str], absent: list[str]
) -> None:
    worker = render(answers(case)) / "backend" / "app" / "worker"
    for name in present:
        assert (worker / name).is_file(), name
    for name in absent:
        assert not (worker / name).exists(), name


@pytest.mark.parametrize("case", list(CASES))
def test_delivery_files_follow_the_answers(render: Render, case: str) -> None:
    project = render(answers(case))
    gitlab = CASES[case].get("ci_provider", "gitlab") == "gitlab"
    assert (project / ".gitlab-ci.yml").is_file() is gitlab
    assert (project / ".github" / "workflows").is_dir() is not gitlab
    kubernetes = CASES[case].get("kubernetes", True)
    assert (project / "kubernetes").is_dir() is kubernetes


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        (
            "defaults",
            {"fastapi", "pydantic", "building-pydantic-ai-agents", "qdrant-clients-sdk", "shadcn"},
        ),
        ("api-only-celery-langgraph", {"fastapi", "pydantic", "langchain-build-agent"}),
        (
            "arq-on-premise-llm",
            {"fastapi", "logfire-instrumentation", "vercel-react-best-practices"},
        ),
    ],
)
def test_skills_follow_the_components(render: Render, case: str, expected: set[str]) -> None:
    lock = tomllib.loads((render(answers(case)) / "skills.lock.toml").read_text(encoding="utf-8"))
    names = {entry["name"] for entry in lock["skill"]}
    assert expected <= names
    if CASES[case].get("vector_database", "qdrant") != "qdrant":
        assert not {n for n in names if n.startswith("qdrant")}
    if CASES[case].get("web_frontend", "react") == "none":
        assert "shadcn" not in names


def test_provider_requires_a_compatible_framework(tmp_path: Path) -> None:
    from conftest import ROOT

    with pytest.raises(ValueError, match="requires Pydantic AI"):
        run_copy(
            str(ROOT),
            tmp_path,
            data={"ai_framework": "langgraph", "llm_provider": "openrouter"},
            defaults=True,
            unsafe=True,
            vcs_ref="HEAD",
            quiet=True,
        )
