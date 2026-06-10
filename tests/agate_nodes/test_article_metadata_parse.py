"""Tests for Article Metadata LLM response parsing."""

from __future__ import annotations

import pytest
from agate_nodes.article_metadata.parse import parse_article_metadata_response


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
