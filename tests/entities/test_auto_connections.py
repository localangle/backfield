"""Tests for automatic connection taxonomy, evidence, and validation."""

from __future__ import annotations

import pytest
from backfield_entities.connections import (
    AUTO_CONNECTION_MIN_CONFIDENCE,
    build_connection_creation_evidence,
    validate_auto_connection_candidate,
)


def test_validate_rejects_endpoint_pair_outside_auto_scope() -> None:
    result = validate_auto_connection_candidate(
        from_entity_type="person",
        to_entity_type="person",
        nature="colleague_of",
        confidence=0.95,
        quote="They worked together.",
    )
    assert result.ok is False
    assert result.skip_reason == "endpoint_pair_not_allowed"


def test_validate_rejects_nature_outside_taxonomy() -> None:
    result = validate_auto_connection_candidate(
        from_entity_type="person",
        to_entity_type="organization",
        nature="custom editorial label",
        confidence=0.95,
        quote="She works at Acme.",
    )
    assert result.ok is False
    assert result.skip_reason == "nature_not_allowed"


def test_validate_rejects_low_confidence() -> None:
    result = validate_auto_connection_candidate(
        from_entity_type="person",
        to_entity_type="organization",
        nature="works_for",
        confidence=0.89,
        quote="She works at Acme.",
    )
    assert result.ok is False
    assert result.skip_reason == "confidence_below_threshold"


def test_validate_rejects_person_location_address_targets() -> None:
    result = validate_auto_connection_candidate(
        from_entity_type="person",
        to_entity_type="location",
        nature="lives_in",
        confidence=0.95,
        quote="She lives at 123 Main St.",
        location_type="address",
    )
    assert result.ok is False
    assert result.skip_reason == "person_location_address_forbidden"


def test_validate_rejects_invalid_location_granularity_for_nature() -> None:
    result = validate_auto_connection_candidate(
        from_entity_type="organization",
        to_entity_type="location",
        nature="located_at",
        confidence=0.95,
        quote="Acme is at 123 Main St.",
        location_type="city",
    )
    assert result.ok is False
    assert result.skip_reason == "location_granularity_not_allowed"


def test_validate_accepts_org_located_at_for_address_like_place() -> None:
    result = validate_auto_connection_candidate(
        from_entity_type="organization",
        to_entity_type="location",
        nature="located_at",
        confidence=0.95,
        quote="Acme is at 123 Main St.",
        location_type="address",
    )
    assert result.ok is True


def test_validate_accepts_person_org_works_for() -> None:
    result = validate_auto_connection_candidate(
        from_entity_type="person",
        to_entity_type="organization",
        nature="works_for",
        confidence=AUTO_CONNECTION_MIN_CONFIDENCE,
        quote="Jane Doe works for Acme Corp.",
    )
    assert result.ok is True


def test_build_connection_creation_evidence_excludes_raw_prompt_fields() -> None:
    evidence = build_connection_creation_evidence(
        confidence=0.95,
        quote="Jane Doe works for Acme Corp.",
        reason="Explicit employment language.",
        from_entity_type="person",
        from_entity_id="person-1",
        from_display_name="Jane Doe",
        to_entity_type="organization",
        to_entity_id="org-1",
        to_display_name="Acme Corp",
        article_id=42,
        run_id="run-1",
        processed_item_id=7,
        adjudication_model="gpt-test",
    )
    payload = evidence.to_storage_dict()
    assert payload["source"] == "dboutput_auto_connections"
    assert payload["confidence"] == 0.95
    assert payload["quote"] == "Jane Doe works for Acme Corp."
    assert payload["article_id"] == 42
    assert "raw_prompt" not in payload
    assert "raw_response" not in payload


def test_build_connection_creation_evidence_rejects_empty_quote() -> None:
    with pytest.raises(ValueError):
        build_connection_creation_evidence(
            confidence=0.95,
            quote="   ",
            reason="Explicit employment language.",
            from_entity_type="person",
            from_entity_id="person-1",
            from_display_name="Jane Doe",
            to_entity_type="organization",
            to_entity_id="org-1",
            to_display_name="Acme Corp",
        )
