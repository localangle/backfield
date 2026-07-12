"""Tests for questionable organization LLM batch parsing."""

from __future__ import annotations

import json
import threading
import time

import pytest
from backfield_entities.quality.llm_questionable_organizations import (
    QuestionableOrganizationCandidate,
    QuestionableOrganizationReviewResult,
    build_questionable_organization_batch_prompt,
    parse_questionable_organization_batch_response,
    review_questionable_organization_batches,
    should_persist_questionable_organization_review,
    trim_sample_mentions_for_prompt,
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


def test_build_questionable_organization_batch_prompt_omits_keep_rows_instruction() -> None:
    prompt = build_questionable_organization_batch_prompt(
        [
            QuestionableOrganizationCandidate(
                canonical_id="org-1",
                label="American civil society",
                slug="american-civil-society",
                organization_type="other",
                prefilter_score=5,
                prefilter_signals=("generic_role_group",),
                linked_count=0,
                mention_count=0,
                sample_mentions=(),
            )
        ]
    )
    assert "Omit rows that are real organizations" in prompt
    assert "flag|unsure" in prompt
    assert "one short sentence" in prompt


def test_build_questionable_organization_batch_prompt_includes_catalog_collision_guidance() -> None:
    prompt = build_questionable_organization_batch_prompt(
        [
            QuestionableOrganizationCandidate(
                canonical_id="org-1",
                label="Gibson Guitars",
                slug="gibson-guitars",
                organization_type="company",
                prefilter_score=5,
                prefilter_signals=("cross_catalog_person", "no_org_anchor"),
                linked_count=2,
                mention_count=3,
                sample_mentions=("Gibson Guitars announced a new line.",),
            )
        ]
    )
    assert "Catalog collisions" in prompt
    assert "Gibson Guitars" in prompt
    assert "catalog_collision=person_canonical_same_label" in prompt
    assert "Glenbard East (school)" in prompt


def test_trim_sample_mentions_for_prompt_caps_count_and_length() -> None:
    long_text = "x" * 300
    trimmed = trim_sample_mentions_for_prompt(
        ("first", "second", long_text, "fourth"),
    )
    assert trimmed == ("first", "second", "x" * 219 + "…")


def test_build_questionable_organization_batch_prompt_uses_trimmed_mentions() -> None:
    long_text = "m" * 300
    prompt = build_questionable_organization_batch_prompt(
        [
            QuestionableOrganizationCandidate(
                canonical_id="org-1",
                label="Example Org",
                slug="example-org",
                organization_type="other",
                prefilter_score=5,
                prefilter_signals=("no_org_anchor",),
                linked_count=0,
                mention_count=3,
                sample_mentions=("short", "middle", long_text),
            )
        ]
    )
    assert "mentions=['short', 'middle', " in prompt
    assert "m" * 219 + "…" in prompt

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


def test_review_questionable_organization_batches_runs_batches_in_parallel() -> None:
    lock = threading.Lock()
    concurrent = {"peak": 0, "current": 0}

    def mock_call_llm(_prompt: str, **_kwargs: object) -> str:
        with lock:
            concurrent["current"] += 1
            concurrent["peak"] = max(concurrent["peak"], concurrent["current"])
        try:
            time.sleep(0.05)
            return json.dumps({"results": []})
        finally:
            with lock:
                concurrent["current"] -= 1

    candidates = [
        QuestionableOrganizationCandidate(
            canonical_id=f"org-{index}",
            label=f"Label {index}",
            slug=f"label-{index}",
            organization_type="other",
            prefilter_score=5,
            prefilter_signals=("no_org_anchor",),
            linked_count=0,
            mention_count=0,
            sample_mentions=(),
        )
        for index in range(4)
    ]

    review_questionable_organization_batches(
        candidates,
        call_llm=mock_call_llm,
        batch_size=1,
        max_workers=4,
    )
    assert concurrent["peak"] >= 2


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
