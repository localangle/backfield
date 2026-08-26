"""Schema contract tests for ``stylebook_connections``."""

from __future__ import annotations

from backfield_db import StylebookConnection


def test_stylebook_connection_open_edge_fields() -> None:
    row = StylebookConnection(
        project_id=1,
        stylebook_id=1,
        from_entity_type="person",
        from_entity_id="person-uuid",
        to_entity_type="organization",
        to_entity_id="org-uuid",
        nature="works_for",
    )
    assert row.nature == "works_for"
    assert row.closed_at is None
    assert row.stylebook_id == 1
    assert row.currentness == "unknown"
    assert row.currentness_as_of is None
    assert row.currentness_evidence_id is None
    assert not hasattr(row, "description") or "description" not in StylebookConnection.model_fields
    assert (
        not hasattr(row, "evidence_json")
        or "evidence_json" not in StylebookConnection.model_fields
    )


def test_stylebook_connection_allows_null_nature() -> None:
    row = StylebookConnection(
        project_id=1,
        stylebook_id=1,
        from_entity_type="person",
        from_entity_id="person-uuid",
        to_entity_type="person",
        to_entity_id="person-uuid-2",
        nature=None,
    )
    assert row.nature is None


def test_stylebook_connection_evidence_defaults() -> None:
    from backfield_db import StylebookConnectionEvidence

    row = StylebookConnectionEvidence(
        connection_id=1,
        description="Jane works for Acme.",
        quote="Jane works for Acme",
        confidence=0.95,
        source="dboutput_auto_connections",
    )
    assert row.article_id is None
    assert row.description is not None
    assert row.asserted_currentness == "unspecified"
    assert row.currentness_review_source == "unreviewed"


def test_stylebook_connection_nature_custom_defaults() -> None:
    from backfield_db import StylebookConnectionNatureCustom

    row = StylebookConnectionNatureCustom(
        stylebook_id=1,
        slug="mentored",
        label="mentored",
        equivalent_to="works_with",
    )
    assert row.temporal_kind == "dynamic"
