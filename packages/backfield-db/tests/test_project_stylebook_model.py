"""Structural contract for strict project Stylebook ownership."""

from __future__ import annotations

from backfield_db import BackfieldProject


def test_project_workspace_and_stylebook_columns_are_required() -> None:
    workspace_column = BackfieldProject.__table__.c.workspace_id
    stylebook_column = BackfieldProject.__table__.c.stylebook_id

    assert workspace_column.nullable is False
    assert stylebook_column.nullable is False
    assert workspace_column.index is True
    assert stylebook_column.index is True
    assert {foreign_key.target_fullname for foreign_key in workspace_column.foreign_keys} == {
        "backfield_workspace.id"
    }
    assert {foreign_key.target_fullname for foreign_key in stylebook_column.foreign_keys} == {
        "stylebook.id"
    }

    constraint_names = {
        constraint.name for constraint in BackfieldProject.__table__.constraints
    }
    assert "fk_backfield_project_org_workspace" in constraint_names
    assert "fk_backfield_project_org_stylebook" in constraint_names
