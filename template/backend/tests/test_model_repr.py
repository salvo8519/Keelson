"""A model's representation never shows a secret column (Keelstone).

Representations end up in logs, tracebacks and debugger output, where the redaction of field
names does not reach. Every mapped model is built with a canary in each column named like a
secret (``is_secret_name``), and its ``repr`` must not show it.
"""

import pytest
from sqlalchemy import inspect

import app.db.models  # noqa: F401 - registers every model
from app.core.logging import is_secret_name
from app.db.base import Base

CANARY = "-".join(("repr", "canary", "77b1"))
MODELS = sorted((mapper.class_ for mapper in Base.registry.mappers), key=lambda model: model.__name__)


def _secret_columns(model: type) -> list[str]:
    return [attribute.key for attribute in inspect(model).column_attrs if is_secret_name(attribute.key)]


def test_some_model_has_a_secret_column() -> None:
    """The check below would pass vacuously if no column were named like a secret."""
    assert any(_secret_columns(model) for model in MODELS)


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_the_representation_of_a_model_hides_its_secret_columns(model: type) -> None:
    instance = model()
    for name in _secret_columns(model):
        setattr(instance, name, CANARY)
    assert CANARY not in repr(instance)
