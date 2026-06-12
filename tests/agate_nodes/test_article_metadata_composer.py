"""Tests for Article Metadata prompt composition."""

from __future__ import annotations

import pytest
from agate_nodes.article_metadata.composer import (
    compose_article_metadata_prompt,
    extract_categories_from_prompt,
    flatten_input,
    resolve_text,
    substitute_prompt_placeholders,
)


def test_extract_categories_from_prompt_section() -> None:
    prompt = """
Intro text.

## Categories
- Local news
- Politics

{text}
"""
    assert extract_categories_from_prompt(prompt) == ["Local news", "Politics"]


def test_extract_temporal_orientation_categories() -> None:
    from agate_nodes.article_metadata.composer import load_package_file

    prompt = load_package_file("prompts/presets/temporal_orientation.md")
    categories = extract_categories_from_prompt(prompt)
    assert categories == [
        "future",
        "present",
        "past",
        "ongoing",
        "cyclical",
        "evergreen",
        "other",
    ]


def test_extract_format_categories() -> None:
    from agate_nodes.article_metadata.composer import load_package_file

    prompt = load_package_file("prompts/presets/format.md")
    categories = extract_categories_from_prompt(prompt)
    assert categories == [
        "news_story",
        "human_interest",
        "profile",
        "in_depth",
        "explainer_analysis",
        "opinion_commentary",
        "review_criticism",
        "guide_service",
        "list_roundup",
        "interview_qa",
        "obituary",
        "multimedia",
        "live_update",
        "other",
    ]


def test_extract_user_need_categories() -> None:
    from agate_nodes.article_metadata.composer import load_package_file

    prompt = load_package_file("prompts/presets/user_need.md")
    categories = extract_categories_from_prompt(prompt)
    assert categories == [
        "update_me",
        "explain_it_to_me",
        "help_me_act",
        "hold_power_to_account",
        "show_me_the_community",
        "move_me",
        "entertain_me",
        "catch_me_up",
        "other",
    ]


def test_extract_information_needs_categories() -> None:
    from agate_nodes.article_metadata.composer import load_package_file

    prompt = load_package_file("prompts/presets/information_needs.md")
    categories = extract_categories_from_prompt(prompt)
    assert categories == [
        "emergencies_risks",
        "health_welfare",
        "education",
        "transportation",
        "economic_opportunities",
        "environment",
        "civic_information",
        "political_information",
        "other",
    ]


def test_compose_information_needs_prompt_requests_json_array() -> None:
    from agate_nodes.article_metadata.composer import load_package_file

    template = load_package_file("prompts/presets/information_needs.md")
    flattened = {"text": "School board votes to close two schools."}
    output_format = load_package_file("prompts/_output_format_subject.json")
    prompt, _categories = compose_article_metadata_prompt(
        prompt_template=template,
        flattened=flattened,
        output_format_json=output_format,
        preset_id="information_needs",
    )
    assert "JSON object with a \"needs\" key containing an array of 1 to 3 objects" in prompt
    assert "School board votes to close two schools." in prompt


def test_extract_geographic_scope_categories() -> None:
    from agate_nodes.article_metadata.composer import load_package_file

    prompt = load_package_file("prompts/presets/geographic_scope.md")
    categories = extract_categories_from_prompt(prompt)
    assert categories == [
        "neighborhood_community",
        "city_municipality",
        "regional",
        "statewide",
        "national",
        "international",
        "elsewhere_to_local",
        "local_to_elsewhere",
        "other",
    ]


def test_extract_subject_categories() -> None:
    from agate_nodes.article_metadata.composer import load_package_file

    prompt = load_package_file("prompts/presets/subject.md")
    categories = extract_categories_from_prompt(prompt)
    assert "local_government_politics" in categories
    assert "pro_sports" in categories
    assert "other" in categories
    assert len(categories) == 42


def test_compose_subject_prompt_requests_json_array() -> None:
    from agate_nodes.article_metadata.composer import load_package_file

    template = load_package_file("prompts/presets/subject.md")
    flattened = {"text": "Council voted on zoning."}
    output_format = load_package_file("prompts/_output_format_subject.json")
    prompt, _categories = compose_article_metadata_prompt(
        prompt_template=template,
        flattened=flattened,
        output_format_json=output_format,
        preset_id="subject",
    )
    assert "JSON object with a \"subjects\" key containing an array of 1 to 3 objects" in prompt
    assert "Council voted on zoning." in prompt


def test_compose_places_article_text_before_output_instructions() -> None:
    from agate_nodes.article_metadata.composer import load_package_file

    template = load_package_file("prompts/presets/user_need.md")
    flattened = {"text": "Council voted Tuesday."}
    output_format = '{"category": "Local news", "rationale": "...", "confidence": 0.5}'
    prompt, _categories = compose_article_metadata_prompt(
        prompt_template=template,
        flattened=flattened,
        output_format_json=output_format,
    )
    assert prompt.index("## Article text") < prompt.index("Council voted Tuesday.")
    assert prompt.index("Council voted Tuesday.") < prompt.index("Return only valid JSON")


def test_compose_includes_headline_placeholder() -> None:
    template = "## Categories\n- Sports\n\nHeadline: {headline}\n\n{text}"
    flattened = {"text": "Body", "headline": "Big game tonight"}
    output_format = '{"category": "Sports", "rationale": "...", "confidence": 0.5}'
    prompt, categories = compose_article_metadata_prompt(
        prompt_template=template,
        flattened=flattened,
        output_format_json=output_format,
    )
    assert "Big game tonight" in prompt
    assert "Body" in prompt
    assert categories == ["Sports"]


def test_resolve_text_requires_non_empty_body() -> None:
    with pytest.raises(ValueError, match="non-empty 'text'"):
        resolve_text({"headline": "Only headline"})


def test_flatten_input_merges_upstream_node_payload() -> None:
    merged = flatten_input({"node-1": {"text": "Story", "url": "https://example.com"}})
    assert merged["text"] == "Story"
    assert merged["url"] == "https://example.com"


def test_substitute_prompt_placeholders_missing_key_becomes_empty() -> None:
    result = substitute_prompt_placeholders("Hello {headline}\n{text}", {"text": "Body"})
    assert "Hello" in result
    assert "Body" in result
