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


def test_parse_subject_unwraps_subjects_wrapper_object() -> None:
    parsed = parse_subject_metadata_response(
        {
            "subjects": [
                {
                    "category": "local_government_politics",
                    "rationale": "Council vote is central.",
                    "confidence": 0.9,
                }
            ]
        },
        allowed_categories=["local_government_politics", "other"],
    )
    assert len(parsed) == 1
    assert parsed[0].category == "local_government_politics"


def test_parse_subject_unwraps_needs_wrapper_object() -> None:
    parsed = parse_subject_metadata_response(
        {
            "needs": [
                {
                    "category": "accountability_government_oversight",
                    "rationale": "Investigates misuse of funds.",
                    "confidence": "0.88",
                }
            ]
        },
        allowed_categories=["accountability_government_oversight", "other"],
    )
    assert parsed[0].category == "accountability_government_oversight"
    assert parsed[0].confidence == 0.88


def test_parse_subject_unwraps_nested_subjects_array() -> None:
    parsed = parse_subject_metadata_response(
        [
            {
                "subjects": [
                    {
                        "category": "local_government_politics",
                        "rationale": "Council vote is central.",
                        "confidence": 0.9,
                    }
                ]
            }
        ],
        allowed_categories=["local_government_politics", "other"],
    )
    assert parsed[0].category == "local_government_politics"


def test_parse_subject_unwraps_article_metadata_wrapper() -> None:
    parsed = parse_subject_metadata_response(
        {
            "article_metadata": {
                "subjects": [
                    {
                        "category": "pro_sports",
                        "rationale": "Game recap is the focus.",
                        "confidence": 0.95,
                    }
                ]
            }
        },
        allowed_categories=["pro_sports", "other"],
    )
    assert parsed[0].category == "pro_sports"


def test_parse_subject_prefers_subjects_wrapper_over_partial_top_level_fields() -> None:
    parsed = parse_subject_metadata_response(
        {
            "confidence": 0.5,
            "subjects": [
                {
                    "category": "community_life",
                    "rationale": "Neighborhood festival coverage.",
                    "confidence": 0.88,
                }
            ],
        },
        allowed_categories=["community_life", "other"],
    )
    assert parsed[0].category == "community_life"
    assert parsed[0].confidence == 0.88


def test_parse_subject_accepts_category_list() -> None:
    parsed = parse_subject_metadata_response(
        [
            {
                "categories": ["local_government_politics"],
                "rationale": "Council vote is central.",
                "confidence": 0.9,
            }
        ],
        allowed_categories=["local_government_politics", "other"],
    )
    assert parsed[0].category == "local_government_politics"


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
