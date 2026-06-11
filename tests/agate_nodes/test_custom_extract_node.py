"""Tests for Custom Extract node runtime."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from agate_runtime.context import AgateEnvContext
from agate_runtime.runners import run_custom_extract_runtime

_PARAMS = {
    "record_type": "ingredients",
    "label": "Ingredients",
    "fields": [
        {"name": "item", "label": "Item", "type": "string"},
        {"name": "quantity", "label": "Quantity", "type": "string"},
    ],
    "instructions": "Extract from the recipe card only.",
}

_LLM_PAYLOAD = {
    "records": [
        {
            "fields": {"item": "flour", "quantity": "2 cups"},
            "mentions": [{"text": "2 cups of flour, sifted", "quote": False}],
            "confidence": 0.95,
        },
        {
            "fields": {"item": "unicorn dust", "quantity": "1 oz"},
            "mentions": [],
        },
    ]
}


def test_run_emits_custom_records_with_passthrough_fields() -> None:
    with patch(
        "agate_nodes.custom_extract.node_port.call_llm",
        return_value=json.dumps(_LLM_PAYLOAD),
    ):
        out = run_custom_extract_runtime(
            _PARAMS,
            {"text": "Recipe body.", "headline": "Best bread", "url": "https://example.com"},
            AgateEnvContext(run_id="run-test"),
        )

    assert out["text"] == "Recipe body."
    assert out["headline"] == "Best bread"
    assert out["url"] == "https://example.com"

    block = out["custom_records"]["ingredients"]
    assert block["label"] == "Ingredients"
    assert [field["name"] for field in block["schema"]] == ["item", "quantity"]
    assert block["dropped_ungrounded"] == 1
    assert len(block["records"]) == 1
    record = block["records"][0]
    assert record["fields"] == {"item": "flour", "quantity": "2 cups"}
    assert record["mentions"] == [{"text": "2 cups of flour, sifted", "quote": False}]
    assert record["confidence"] == 0.95
    assert record["key"]


def test_serial_chain_accumulates_record_types() -> None:
    upstream_records = {
        "recipe_steps": {
            "label": "Recipe steps",
            "schema": [{"name": "step", "label": "Step", "type": "string", "description": ""}],
            "records": [],
            "dropped_ungrounded": 0,
        }
    }
    with patch(
        "agate_nodes.custom_extract.node_port.call_llm",
        return_value=json.dumps(_LLM_PAYLOAD),
    ):
        out = run_custom_extract_runtime(
            _PARAMS,
            {"text": "Recipe body.", "custom_records": upstream_records},
            AgateEnvContext(run_id="run-test"),
        )

    assert set(out["custom_records"].keys()) == {"recipe_steps", "ingredients"}


def test_missing_record_type_fails_with_clear_error() -> None:
    with pytest.raises(ValueError, match="Record type"):
        run_custom_extract_runtime(
            {"fields": [{"name": "item"}]},
            {"text": "Recipe body."},
            AgateEnvContext(run_id="run-test"),
        )


def test_malformed_llm_json_fails_with_clear_error() -> None:
    with patch(
        "agate_nodes.custom_extract.node_port.call_llm",
        return_value="not json at all",
    ):
        with pytest.raises(ValueError, match="Failed to parse LLM response"):
            run_custom_extract_runtime(
                _PARAMS,
                {"text": "Recipe body."},
                AgateEnvContext(run_id="run-test"),
            )
