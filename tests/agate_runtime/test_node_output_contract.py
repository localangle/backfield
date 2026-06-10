"""Tests for run JSON contribution projection."""

from __future__ import annotations

from agate_runtime.node_output_contract import (
    project_gathered_contributions,
    project_node_contribution,
)


def test_project_article_metadata_strips_article_passthrough() -> None:
    projected = project_node_contribution(
        "ArticleMetadata",
        {
            "text": "Story body.",
            "headline": "Council vote",
            "article_metadata": {
                "meta_type": "information_needs",
                "category": "political_information",
                "confidence": 0.92,
            },
        },
    )
    assert projected == {
        "article_metadata": {
            "meta_type": "information_needs",
            "category": "political_information",
            "confidence": 0.92,
        }
    }


def test_project_embed_images_keeps_embeddings_only() -> None:
    projected = project_node_contribution(
        "EmbedImages",
        {
            "images": [{"id": "image:1", "url": "https://example.com/a.png"}],
            "image_embeddings": [{"id": "image:1", "embedding": [0.1, 0.2]}],
        },
    )
    assert projected == {"image_embeddings": [{"id": "image:1", "embedding": [0.1, 0.2]}]}


def test_project_gathered_uses_public_slugs_and_contributions() -> None:
    projected = project_gathered_contributions(
        {
            "node-7": {
                "headline": "Title",
                "text": "Body",
            },
            "node-11": {
                "headline": "Title",
                "text": "Body",
                "article_metadata": {"category": "political_information"},
            },
        },
        source_id_to_type={
            "node-7": "JSONInput",
            "node-11": "ArticleMetadata",
        },
        source_id_to_public={
            "node-7": "json_input",
            "node-11": "article_metadata",
        },
    )
    assert projected["json_input"]["headline"] == "Title"
    assert "text" not in projected["article_metadata"]
    assert projected["article_metadata"]["article_metadata"]["category"] == "political_information"
