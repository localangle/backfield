"""Tests for EmbedText article text composition."""

from __future__ import annotations

import pytest
from agate_nodes.embed_text.composer import (
    DEFAULT_EMBED_INPUT_TOKEN_BUDGET,
    compose_article_embed_text,
)
from backfield_ai.token_budget import count_tokens


def test_compose_includes_headline_and_text() -> None:
    result, truncated = compose_article_embed_text(
        {"text": "Body copy.", "headline": "A headline", "url": "https://example.com"}
    )
    assert truncated is False
    assert "A headline" in result
    assert "Body copy." in result
    assert "https://example.com" in result


def test_compose_requires_text() -> None:
    with pytest.raises(ValueError, match="non-empty upstream text"):
        compose_article_embed_text({"headline": "Only headline"})


def test_compose_truncates_long_body() -> None:
    long_body = ("Paragraph one. " * 400) + "\n\n" + ("Paragraph two. " * 400)
    result, truncated = compose_article_embed_text(
        {"text": long_body, "headline": "Headline"},
        max_input_tokens=200,
    )
    assert truncated is True
    assert "Headline" in result
    assert len(result) < len(long_body)


def test_compose_keeps_dense_text_within_the_embedding_limit() -> None:
    """Numbers and non-English text use far more tokens per character than prose."""
    dense_samples = {
        "numbers": "1048 2291 3375 4410 " * 6000,
        "japanese": "東京都議会は本日予算案を可決した。" * 3000,
        "urls": "https://example.com/a/b?id=9876&ref=x7 " * 4000,
    }
    for name, body in dense_samples.items():
        result, truncated = compose_article_embed_text({"text": body, "headline": "Headline"})
        assert truncated is True, name
        assert count_tokens(result) <= DEFAULT_EMBED_INPUT_TOKEN_BUDGET, name
        assert count_tokens(result) < 8192, name


def test_compose_truncates_body_but_keeps_headline_and_metadata() -> None:
    result, truncated = compose_article_embed_text(
        {
            "text": "Long body sentence. " * 5000,
            "headline": "Keep this headline",
            "url": "https://example.com/keep-this-url",
            "meta_topic": "Keep this topic",
        },
        max_input_tokens=300,
    )
    assert truncated is True
    assert result.startswith("Keep this headline")
    assert result.endswith("Keep this topic")
    assert "https://example.com/keep-this-url" in result
    assert count_tokens(result) <= 300


def test_compose_hard_limits_oversized_metadata() -> None:
    result, truncated = compose_article_embed_text(
        {"text": "Short body.", "meta_notes": "note " * 2000},
        max_input_tokens=200,
    )
    assert truncated is True
    assert count_tokens(result) <= 200


def test_compose_treats_special_token_text_as_plain_text() -> None:
    result, truncated = compose_article_embed_text({"text": "Before <|endoftext|> after."})
    assert truncated is False
    assert "<|endoftext|>" in result


def test_compose_leaves_short_articles_unchanged() -> None:
    result, truncated = compose_article_embed_text({"text": "Short body.", "headline": "Head"})
    assert truncated is False
    assert result == "Head\n\nShort body."
