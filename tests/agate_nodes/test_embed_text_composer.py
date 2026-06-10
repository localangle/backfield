"""Tests for EmbedText article text composition."""

from __future__ import annotations

import pytest
from agate_nodes.embed_text.composer import compose_article_embed_text


def test_compose_includes_headline_and_text() -> None:
    result = compose_article_embed_text(
        {"text": "Body copy.", "headline": "A headline", "url": "https://example.com"}
    )
    assert "A headline" in result
    assert "Body copy." in result
    assert "https://example.com" in result


def test_compose_requires_text() -> None:
    with pytest.raises(ValueError, match="non-empty upstream text"):
        compose_article_embed_text({"headline": "Only headline"})
