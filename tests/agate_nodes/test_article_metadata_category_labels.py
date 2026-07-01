"""Tests for Article Metadata category label enforcement."""

from __future__ import annotations

import pytest
from agate_nodes.article_metadata.category_labels import (
    format_allowed_categories_enforcement,
    fuzzy_match_allowed_category,
    normalize_category_token,
    resolve_allowed_category,
)
from agate_nodes.article_metadata.parse import (
    parse_article_metadata_response,
    parse_subject_metadata_response,
)


def test_format_allowed_categories_enforcement_lists_exact_slugs() -> None:
    block = format_allowed_categories_enforcement(
        ["pro_sports", "college_sports", "other"]
    )
    assert "## Allowed category values" in block
    assert "`pro_sports`" in block
    assert "economic_business" in block
    assert "Complete allowed slug list" in block


def test_fuzzy_match_economic_business_to_business_economy() -> None:
    allowed = {"business_economy", "other"}
    assert fuzzy_match_allowed_category("economic_business", allowed) == "business_economy"


def test_resolve_economic_business_alias() -> None:
    allowed = {"business_economy", "other"}
    assert resolve_allowed_category("economic_business", allowed) == "business_economy"


def test_parse_topic_maps_economic_business() -> None:
    parsed = parse_subject_metadata_response(
        [
            {
                "category": "economic_business",
                "rationale": "Retail expansion and downtown hiring plans.",
                "confidence": 0.9,
            }
        ],
        allowed_categories=["business_economy", "other"],
    )
    assert parsed[0].category == "business_economy"


def test_parse_fallback_to_other_when_enabled() -> None:
    parsed = parse_subject_metadata_response(
        [
            {
                "category": "totally_unknown_slug",
                "rationale": "Nothing matches.",
                "confidence": 0.4,
            }
        ],
        allowed_categories=["business_economy", "other"],
        fallback_to_other=True,
    )
    assert parsed[0].category == "other"


def test_normalize_category_token() -> None:
    assert normalize_category_token("Pro Sports") == "pro_sports"
    assert normalize_category_token("college-sports") == "college_sports"


def test_resolve_allowed_category_case_and_separator() -> None:
    allowed = {"pro_sports", "other"}
    assert resolve_allowed_category("Pro_Sports", allowed) == "pro_sports"


def test_resolve_generic_sports_defaults_to_pro_sports() -> None:
    allowed = {"pro_sports", "college_sports", "prep_youth_sports", "other"}
    assert (
        resolve_allowed_category(
            "sports",
            allowed,
            rationale="Professional baseball game recap.",
        )
        == "pro_sports"
    )


def test_resolve_generic_sports_uses_college_hint() -> None:
    allowed = {"pro_sports", "college_sports", "prep_youth_sports", "other"}
    assert (
        resolve_allowed_category(
            "sport",
            allowed,
            rationale="NCAA tournament upset in the Big Ten.",
        )
        == "college_sports"
    )


def test_parse_subject_maps_generic_sports_to_allowed_slug() -> None:
    parsed = parse_subject_metadata_response(
        [
            {
                "category": "sports",
                "rationale": "Twins walk-off win clinches the division title.",
                "confidence": 0.95,
            }
        ],
        allowed_categories=["pro_sports", "college_sports", "prep_youth_sports", "other"],
    )
    assert parsed[0].category == "pro_sports"


def test_rejects_unknown_category_after_resolution() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        parse_article_metadata_response(
            {"category": "weather", "rationale": "Rain.", "confidence": 0.5},
            allowed_categories=["pro_sports", "other"],
        )
