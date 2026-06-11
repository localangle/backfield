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
