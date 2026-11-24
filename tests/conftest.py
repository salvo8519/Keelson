"""Shared fixtures: render the template with Copier into a temporary directory."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from copier import run_copy

ROOT = Path(__file__).resolve().parents[1]

Render = Callable[[dict[str, Any]], Path]


@pytest.fixture(scope="session")
def render(tmp_path_factory: pytest.TempPathFactory) -> Render:
    """Render the working tree (uncommitted changes included) with the given answers.

    Results are cached per set of answers for the whole session.
    """
    cache: dict[tuple[tuple[str, Any], ...], Path] = {}

    def _render(answers: dict[str, Any]) -> Path:
        key = tuple(sorted(answers.items()))
        if key not in cache:
            dst = tmp_path_factory.mktemp("render")
            run_copy(
                str(ROOT),
                dst,
                data=answers,
                defaults=True,
                unsafe=True,
                vcs_ref="HEAD",
                quiet=True,
            )
            cache[key] = dst
        return cache[key]

    return _render
