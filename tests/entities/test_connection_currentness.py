"""Currentness summary rules for Stylebook connections."""

from __future__ import annotations

from datetime import UTC, datetime

from backfield_db import StylebookConnection, StylebookConnectionEvidence
from backfield_entities.connections.writer import _apply_currentness_summary


def _connection() -> StylebookConnection:
    return StylebookConnection(
        project_id=1,
        stylebook_id=1,
        from_entity_type="person",
        from_entity_id="person-1",
        to_entity_type="organization",
        to_entity_id="org-1",
        nature="works_for",
        currentness="current",
        currentness_as_of=datetime(2025, 1, 1, tzinfo=UTC),
        currentness_evidence_id=1,
    )


def _evidence(
    *,
    evidence_id: int,
    asserted_currentness: str,
    observed_at: datetime,
) -> StylebookConnectionEvidence:
    return StylebookConnectionEvidence(
        id=evidence_id,
        connection_id=1,
        asserted_currentness=asserted_currentness,
        observed_at=observed_at,
    )


def test_older_or_unspecified_evidence_does_not_change_currentness() -> None:
    connection = _connection()

    _apply_currentness_summary(
        connection,
        _evidence(
            evidence_id=2,
            asserted_currentness="former",
            observed_at=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        is_dynamic=True,
    )
    _apply_currentness_summary(
        connection,
        _evidence(
            evidence_id=3,
            asserted_currentness="unspecified",
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        is_dynamic=True,
    )

    assert connection.currentness == "current"
    assert connection.currentness_as_of == datetime(2025, 1, 1, tzinfo=UTC)
    assert connection.currentness_evidence_id == 1


def test_newer_explicit_evidence_updates_dynamic_currentness() -> None:
    connection = _connection()
    evidence = _evidence(
        evidence_id=4,
        asserted_currentness="former",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    _apply_currentness_summary(connection, evidence, is_dynamic=True)

    assert connection.currentness == "former"
    assert connection.currentness_as_of == datetime(2026, 1, 1, tzinfo=UTC)
    assert connection.currentness_evidence_id == 4


def test_same_time_conflict_preserves_existing_summary() -> None:
    connection = _connection()

    _apply_currentness_summary(
        connection,
        _evidence(
            evidence_id=4,
            asserted_currentness="former",
            observed_at=datetime(2025, 1, 1, tzinfo=UTC),
        ),
        is_dynamic=True,
    )

    assert connection.currentness == "current"
    assert connection.currentness_evidence_id == 1


def test_static_nature_clears_currentness_summary() -> None:
    connection = _connection()

    _apply_currentness_summary(
        connection,
        _evidence(
            evidence_id=5,
            asserted_currentness="current",
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        is_dynamic=False,
    )

    assert connection.currentness == "unknown"
    assert connection.currentness_as_of is None
    assert connection.currentness_evidence_id is None
