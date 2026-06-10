"""Tests for Article Metadata LLM response parsing."""

from __future__ import annotations

import pytest
from agate_nodes.article_metadata.parse import (
    parse_article_metadata_response,
    parse_subject_metadata_response,
)


def test_parse_valid_response() -> None:
    parsed = parse_article_metadata_response(
        {
            "category": "Politics",
            "rationale": "Centers on an election.",
            "confidence": 0.91,
        },
        allowed_categories=["Politics", "Sports"],
    )
    assert parsed.category == "Politics"
    assert parsed.confidence == 0.91


def test_rejects_category_not_in_prompt_list() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        parse_article_metadata_response(
            {
                "category": "Weather",
                "rationale": "Mentions rain.",
                "confidence": 0.4,
            },
            allowed_categories=["Politics", "Sports"],
        )


def test_rejects_confidence_out_of_range() -> None:
    with pytest.raises(ValueError, match="confidence"):
        parse_article_metadata_response(
            {
                "category": "Politics",
                "rationale": "Centers on an election.",
                "confidence": 1.2,
            },
            allowed_categories=["Politics"],
        )


def test_parse_subject_array_response() -> None:
    parsed = parse_subject_metadata_response(
        [
            {
                "category": "local_government_politics",
                "rationale": "Council vote is central.",
                "confidence": 0.9,
            },
            {
                "category": "housing_affordability_homelessness",
                "rationale": "Affordable housing is a major theme.",
                "confidence": 0.85,
            },
        ],
        allowed_categories=[
            "local_government_politics",
            "housing_affordability_homelessness",
            "other",
        ],
    )
    assert len(parsed) == 2
    assert parsed[0].category == "local_government_politics"
    assert parsed[1].category == "housing_affordability_homelessness"


def test_parse_subject_accepts_legacy_subject_keys() -> None:
    parsed = parse_subject_metadata_response(
        [
            {
                "subject": "pro_sports",
                "subject_rationale": "Game outcome is the focus.",
                "subject_confidence": 0.97,
            }
        ],
        allowed_categories=["pro_sports", "other"],
    )
    assert parsed[0].category == "pro_sports"


def test_rejects_more_than_three_subjects() -> None:
    with pytest.raises(ValueError, match="At most 3"):
        parse_subject_metadata_response(
            [
                {"category": "travel", "rationale": "a", "confidence": 0.5},
                {"category": "other", "rationale": "b", "confidence": 0.5},
                {"category": "recipes", "rationale": "c", "confidence": 0.5},
                {"category": "obituaries", "rationale": "d", "confidence": 0.5},
            ],
            allowed_categories=["travel", "other", "recipes", "obituaries"],
        )
