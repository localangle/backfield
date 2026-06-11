"""Tests for DBOutput consolidation helpers."""

from __future__ import annotations

from agate_runtime.output_node import consolidated_body_from_dboutput


def test_consolidated_body_expands_gathered_payload() -> None:
    body = consolidated_body_from_dboutput(
        {},
        {
            "gather-1": {
                "gathered": {
                    "node-7": {
                        "headline": "Title",
                        "text": "Body",
                    },
                    "node-11": {
                        "headline": "Title",
                        "text": "Body",
                        "article_metadata": {
                            "meta_type": "information_needs",
                            "category": "political_information",
                            "confidence": 0.92,
                        },
                    },
                }
            }
        },
    )
    assert body["headline"] == "Title"
    assert body["text"] == "Body"
    assert body["article_metadata"]["category"] == "political_information"
    assert "gathered" not in body


def test_custom_records_from_parallel_branches_union_record_types() -> None:
    ingredients = {"label": "Ingredients", "schema": [], "records": [], "dropped_ungrounded": 0}
    steps = {"label": "Recipe steps", "schema": [], "records": [], "dropped_ungrounded": 0}
    body = consolidated_body_from_dboutput(
        {},
        {
            "gather-1": {
                "gathered": {
                    "node-7": {
                        "text": "Body",
                        "custom_records": {"ingredients": ingredients},
                    },
                    "node-11": {
                        "text": "Body",
                        "custom_records": {"recipe_steps": steps},
                    },
                }
            }
        },
    )
    assert set(body["custom_records"].keys()) == {"ingredients", "recipe_steps"}


def test_custom_records_from_direct_parallel_upstreams_union_record_types() -> None:
    body = consolidated_body_from_dboutput(
        {},
        {
            "node-7": {
                "text": "Body",
                "custom_records": {"ingredients": {"label": "Ingredients", "records": []}},
            },
            "node-11": {
                "text": "Body",
                "custom_records": {"recipe_steps": {"label": "Recipe steps", "records": []}},
            },
        },
    )
    assert set(body["custom_records"].keys()) == {"ingredients", "recipe_steps"}


def test_dboutput_consolidates_all_node_outputs_not_only_direct_upstreams() -> None:
    """Embed-only DBOutput wiring still carries article text, places, and metadata."""
    body = consolidated_body_from_dboutput(
        {},
        {
            "s3": {
                "headline": "Shooting in Country Club Hills",
                "text": "Story body from S3.",
                "url": "https://example.com/story",
            },
            "geo": {
                "places": {
                    "areas": {"cities": [{"location": "Country Club Hills, IL"}]},
                    "points": [],
                },
            },
            "meta-subject": {
                "article_metadata": {
                    "meta_type": "subject",
                    "category": "public_safety_crime",
                    "rationale": "Crime story.",
                    "confidence": 0.82,
                }
            },
            "meta-format": {
                "article_metadata": {
                    "meta_type": "format",
                    "category": "news_story",
                    "rationale": "News report.",
                    "confidence": 0.78,
                }
            },
            "embed-text": {
                "article_embedding": {"embedded_text": "Story body from S3.", "embedding": [0.1]},
            },
            "embed-images": {
                "image_embeddings": [{"image_id": "image:abc", "embedding": [0.2]}],
            },
        },
    )
    assert body["text"] == "Story body from S3."
    assert body["headline"] == "Shooting in Country Club Hills"
    assert "places" in body
    assert body["article_metadata"]["meta_type"] == "format"
    assert len(body["article_metadata_all"]) == 2
    assert body["article_embedding"]["embedded_text"] == "Story body from S3."
    assert body["image_embeddings"][0]["image_id"] == "image:abc"
