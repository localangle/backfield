"""Tests for prompt placeholder substitution."""

from __future__ import annotations

import pytest
from agate_utils.prompt_placeholders import extract_json_path, substitute_prompt_placeholders


def test_substitute_flat_and_nested_paths() -> None:
    flattened = {
        "text": "Story body.",
        "url": "https://example.com",
        "results": [{"caption": "One", "id": 1}, {"caption": "Two", "id": 2}],
    }
    prompt = substitute_prompt_placeholders(
        "URL: {url}\nCaptions:\n{results.caption}",
        flattened,
    )
    assert "URL: https://example.com" in prompt
    assert '"One"' in prompt
    assert '"Two"' in prompt


def test_substitute_raw_and_escaped_braces() -> None:
    flattened = {"text": "Hello", "score": 3}
    prompt = substitute_prompt_placeholders("Input: {raw}\nLiteral {{text}} stays.", flattened)
    assert '"text": "Hello"' in prompt
    assert "{text}" in prompt


def test_extract_json_path_multi_field_array() -> None:
    flattened = {"results": [{"caption": "A", "id": 1}, {"caption": "B", "id": 2}]}
    picked = extract_json_path(flattened, "results.caption, id")
    assert picked == [{"caption": "A", "id": 1}, {"caption": "B", "id": 2}]


def test_missing_path_raises() -> None:
    with pytest.raises(ValueError, match="not found in input"):
        extract_json_path({"text": "Hi"}, "missing.path")
