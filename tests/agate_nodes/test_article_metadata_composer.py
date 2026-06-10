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
