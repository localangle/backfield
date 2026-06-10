"""Schema contract tests for substrate_article_meta."""

from __future__ import annotations

from backfield_db import SubstrateArticleMeta
from sqlalchemy import UniqueConstraint


def _unique_constraint_columns(model: type[object], name: str) -> tuple[str, ...]:
    table = model.__table__
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name == name:
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"Unique constraint {name!r} not found on {table.name}")


def test_article_meta_one_row_per_article_and_meta_type() -> None:
    assert _unique_constraint_columns(
        SubstrateArticleMeta,
        "uq_substrate_article_meta_article_id_meta_type",
    ) == ("article_id", "meta_type")
