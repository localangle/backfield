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
