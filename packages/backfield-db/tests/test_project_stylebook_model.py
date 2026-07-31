"""Structural contract for additive project Stylebook ownership."""

from __future__ import annotations

from backfield_db import BackfieldProject


def test_project_stylebook_column_is_nullable_indexed_foreign_key() -> None:
    column = BackfieldProject.__table__.c.stylebook_id

    assert column.nullable is True
    assert column.index is True
    assert {foreign_key.target_fullname for foreign_key in column.foreign_keys} == {"stylebook.id"}
