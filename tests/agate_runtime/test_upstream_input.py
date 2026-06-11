"""Tests for upstream input flattening."""

from __future__ import annotations

from agate_nodes.custom_extract.composer import flatten_input, resolve_text
from agate_runtime.upstream_input import expand_gathered_payload, flatten_upstream_inputs


def test_flatten_upstream_inputs_expands_gathered_branch_payloads() -> None:
    flattened = flatten_upstream_inputs(
        {
            "node-14": {
                "gathered": {
                    "node-7": {"text": "Article body", "headline": "Title"},
                    "node-11": {
                        "text": "Article body",
                        "article_metadata": {"category": "political_information"},
                    },
                }
            }
        }
    )
    assert flattened["text"] == "Article body"
    assert flattened["headline"] == "Title"
    assert flattened["article_metadata"]["category"] == "political_information"
    assert "gathered" not in flattened


def test_custom_extract_resolve_text_after_gather() -> None:
    flattened = flatten_input(
        {
            "node-14": {
                "gathered": {
                    "node-7": {"text": "Recipe body", "headline": "Best bread"},
                    "node-11": {"locations": []},
                }
            }
        }
    )
    assert resolve_text(flattened) == "Recipe body"


def test_expand_gathered_unions_custom_records() -> None:
    expanded = expand_gathered_payload(
        {
            "gathered": {
                "node-7": {
                    "text": "Body",
                    "custom_records": {"ingredients": {"records": []}},
                },
                "node-11": {
                    "text": "Body",
                    "custom_records": {"recipe_steps": {"records": []}},
                },
            }
        }
    )
    assert set(expanded["custom_records"].keys()) == {"ingredients", "recipe_steps"}
