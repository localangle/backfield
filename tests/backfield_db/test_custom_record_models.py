"""Schema contract tests for substrate_custom_record."""

from __future__ import annotations

from backfield_db import SubstrateCustomRecord
from sqlalchemy import UniqueConstraint


def _unique_constraint_columns(model: type[object], name: str) -> tuple[str, ...]:
    table = model.__table__
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name == name:
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"Unique constraint {name!r} not found on {table.name}")


def test_custom_record_unique_on_article_type_and_index() -> None:
    assert _unique_constraint_columns(
        SubstrateCustomRecord,
        "uq_substrate_custom_record_article_type_index",
    ) == ("article_id", "record_type", "record_index")


def test_custom_record_json_columns_are_required() -> None:
    table = SubstrateCustomRecord.__table__
    for column_name in ("fields_json", "mentions_json", "field_schema_json"):
        assert table.columns[column_name].nullable is False
