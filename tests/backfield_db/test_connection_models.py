"""Schema contract tests for ``stylebook_connections``."""

from __future__ import annotations

from backfield_db import StylebookConnection


def test_stylebook_connection_description_defaults_to_none() -> None:
    row = StylebookConnection(
        project_id=1,
        from_entity_type="person",
        from_entity_id="person-uuid",
        to_entity_type="organization",
        to_entity_id="org-uuid",
        nature="works_for",
        description="Jane Doe works for Acme Corp.",
    )
    assert row.description == "Jane Doe works for Acme Corp."
    assert row.nature == "works_for"


def test_stylebook_connection_allows_null_nature_with_description() -> None:
    row = StylebookConnection(
        project_id=1,
        from_entity_type="person",
        from_entity_id="person-uuid",
        to_entity_type="person",
        to_entity_id="person-uuid-2",
        nature=None,
        description="They served together on the police reform task force.",
    )
    assert row.nature is None
    assert row.description is not None
