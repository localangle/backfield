"""Unit tests for Stylebook cache adjudication JSON schema."""

from __future__ import annotations

from agate_nodes.geocode_agent.nodes.cache_adjudication import StylebookCacheAdjudicationAnswer


def test_stylebook_cache_adjudication_answer_json_roundtrip() -> None:
    raw = (
        '{"chosen_canonical_id": "550e8400-e29b-41d4-a716-446655440000", '
        '"needs_review": false, "rationale": "Same city label"}'
    )
    ans = StylebookCacheAdjudicationAnswer.model_validate_json(raw)
    assert ans.chosen_canonical_id == "550e8400-e29b-41d4-a716-446655440000"
    assert ans.needs_review is False


def test_stylebook_cache_adjudication_none_choice() -> None:
    raw = '{"chosen_canonical_id": null, "needs_review": true, "rationale": "ambiguous"}'
    ans = StylebookCacheAdjudicationAnswer.model_validate_json(raw)
    assert ans.chosen_canonical_id is None
    assert ans.needs_review is True
