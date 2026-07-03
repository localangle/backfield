"""Tests for questionable organization LLM batch parsing."""

from __future__ import annotations

import json

import pytest
from backfield_entities.quality.llm_questionable_organizations import (
    QuestionableOrganizationCandidate,
    QuestionableOrganizationReviewResult,
    parse_questionable_organization_batch_response,
    review_questionable_organization_batches,
    should_persist_questionable_organization_review,
)


def test_parse_questionable_organization_batch_response_accepts_valid_rows() -> None:
    data = {
        "results": [
            {
                "canonical_id": "org-1",
                "decision": "flag",
                "category": "person_like",
                "confidence": "high",
                "explanation": "Looks like a person, not an institution.",
                "suggested_entity_type": "person",
            },
            {
                "canonical_id": "org-2",
                "decision": "keep",
                "category": "other_non_organization",
                "confidence": "high",
                "explanation": "Named government department.",
                "suggested_entity_type": "none",
            },
        ]
    }
    parsed = parse_questionable_organization_batch_response(
        data,
        valid_ids={"org-1", "org-2"},
    )
    assert set(parsed) == {"org-1", "org-2"}
    assert parsed["org-1"].decision == "flag"
    assert parsed["org-2"].decision == "keep"


def test_parse_questionable_organization_batch_response_ignores_invalid_rows() -> None:
    data = {
        "results": [
            {
                "canonical_id": "org-1",
                "decision": "flag",
                "category": "person_like",
                "confidence": "high",
                "explanation": "Valid row.",
                "suggested_entity_type": "person",
            },
            {
                "canonical_id": "org-2",
                "decision": "maybe",
                "category": "person_like",
                "confidence": "high",
                "explanation": "Invalid decision.",
                "suggested_entity_type": "person",
            },
            {
                "canonical_id": "org-3",
                "decision": "flag",
                "category": "person_like",
                "confidence": "high",
                "explanation": "",
                "suggested_entity_type": "person",
            },
            {
                "canonical_id": "unknown",
                "decision": "flag",
                "category": "person_like",
                "confidence": "high",
                "explanation": "Not in valid ids.",
                "suggested_entity_type": "person",
            },
        ]
    }
    parsed = parse_questionable_organization_batch_response(
        data,
        valid_ids={"org-1", "org-2", "org-3"},
    )
    assert parsed == {
        "org-1": QuestionableOrganizationReviewResult(
            canonical_id="org-1",
            decision="flag",
            category="person_like",
            confidence="high",
            explanation="Valid row.",
            suggested_entity_type="person",
        )
    }


def test_parse_questionable_organization_batch_response_handles_bad_payload() -> None:
    assert parse_questionable_organization_batch_response(None, valid_ids=set()) == {}
    assert parse_questionable_organization_batch_response({}, valid_ids=set()) == {}
    assert (
        parse_questionable_organization_batch_response(
            {"results": "not-a-list"},
            valid_ids=set(),
        )
        == {}
    )
    assert json.loads('{"results":[]}') == {"results": []}


def test_review_questionable_organization_batches_raises_when_all_batches_fail() -> None:
    def failing_call_llm(_prompt: str, **_kwargs: object) -> str:
        raise ValueError("OPENAI_API_KEY must be provided")

    candidates = [
        QuestionableOrganizationCandidate(
            canonical_id="org-1",
            label="Donald Trump",
            slug="donald-trump",
            organization_type="government",
            prefilter_score=5,
            prefilter_signals=("cross_catalog_person",),
            linked_count=0,
            mention_count=0,
            sample_mentions=(),
        )
    ]
    with pytest.raises(RuntimeError, match="failed for all batches"):
        review_questionable_organization_batches(
            candidates,
            call_llm=failing_call_llm,
        )


@pytest.mark.parametrize(
    ("decision", "confidence", "expected"),
    [
        ("flag", "low", True),
        ("keep", "high", False),
        ("unsure", "high", True),
        ("unsure", "medium", True),
        ("unsure", "low", False),
    ],
)
def test_should_persist_questionable_organization_review(
    decision: str,
    confidence: str,
    expected: bool,
) -> None:
    result = QuestionableOrganizationReviewResult(
        canonical_id="org-1",
        decision=decision,  # type: ignore[arg-type]
        category="person_like",
        confidence=confidence,  # type: ignore[arg-type]
        explanation="Example",
        suggested_entity_type="person",
    )
    assert should_persist_questionable_organization_review(result) is expected
