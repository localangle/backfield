"""Tests for EmbedText article text composition."""

from __future__ import annotations

import pytest
from agate_nodes.embed_text.composer import compose_article_embed_text


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
        body_token_budget=200,
    )
    assert truncated is True
    assert "Headline" in result
    assert len(result) < len(long_body)
