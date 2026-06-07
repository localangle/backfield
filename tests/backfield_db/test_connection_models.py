"""Schema contract tests for ``stylebook_connections``."""

from __future__ import annotations

from backfield_db import StylebookConnection
from sqlalchemy import UniqueConstraint


def _unique_constraint_columns(model: type[object], name: str) -> tuple[str, ...]:
    table = model.__table__
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name == name:
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"Unique constraint {name!r} not found on {table.name}")


def test_stylebook_connection_exact_edge_is_unique_per_project() -> None:
    assert _unique_constraint_columns(
        StylebookConnection,
        "uq_stylebook_connection_exact_edge",
    ) == (
        "project_id",
        "from_entity_type",
        "from_entity_id",
        "to_entity_type",
        "to_entity_id",
        "nature",
    )


def test_stylebook_connection_evidence_json_defaults_to_none() -> None:
    row = StylebookConnection(
        project_id=1,
        from_entity_type="person",
        from_entity_id="person-uuid",
        to_entity_type="organization",
        to_entity_id="org-uuid",
        nature="works_for",
    )
    assert row.evidence_json is None
