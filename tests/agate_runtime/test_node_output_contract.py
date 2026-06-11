"""Tests for run JSON contribution projection."""

from __future__ import annotations

from agate_runtime.node_output_contract import (
    project_gathered_branch_refs,
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


def test_project_custom_extract_keeps_custom_records_only() -> None:
    projected = project_node_contribution(
        "CustomExtract",
        {
            "text": "Recipe body.",
            "headline": "Best bread",
            "custom_records": {
                "ingredients": {"label": "Ingredients", "records": [], "dropped_ungrounded": 0}
            },
        },
    )
    assert projected == {
        "custom_records": {
            "ingredients": {"label": "Ingredients", "records": [], "dropped_ungrounded": 0}
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


def test_project_dboutput_keeps_full_consolidated_payload() -> None:
    output = {
        "success": True,
        "article_id": 7,
        "headline": "Council vote",
        "text": "Story body.",
        "locations": [],
    }
    assert project_node_contribution("DBOutput", output) == output


def test_project_gathered_branch_refs_uses_execution_order() -> None:
    refs = project_gathered_branch_refs(
        {
            "node-7": {"headline": "Title", "text": "Body"},
            "node-11": {"article_metadata": {"category": "political_information"}},
            "node-12": {"image_embeddings": [{"id": "image:1"}]},
        },
        source_id_to_public={
            "node-7": "json_input",
            "node-11": "article_metadata",
            "node-12": "embed_images",
        },
        execution_order=["node-7", "node-11", "node-12", "gather-1"],
    )
    assert refs == ["json_input", "article_metadata", "embed_images"]
