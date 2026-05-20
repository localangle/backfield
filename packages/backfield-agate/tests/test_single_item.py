"""Unit tests for single-item ingress helpers."""

from __future__ import annotations

import json

import pytest
from agate_runtime.single_item import build_single_item_input_from_graph_spec_json


def test_build_from_text_input() -> None:
    spec = json.dumps(
        {
            "name": "t",
            "nodes": [
                {"id": "a", "type": "TextInput", "params": {"text": " Hello "}},
                {"id": "b", "type": "Output", "params": {}},
            ],
            "edges": [],
        }
    )
    doc, source = build_single_item_input_from_graph_spec_json(spec)
    assert doc == {"text": " Hello "}
    assert source == "inline:text"


def test_build_from_json_input() -> None:
    spec = json.dumps(
        {
            "name": "j",
            "nodes": [
                {
                    "id": "a",
                    "type": "JSONInput",
                    "params": {"headline": "Hi", "text": "Body copy here."},
                },
            ],
            "edges": [],
        }
    )
    doc, source = build_single_item_input_from_graph_spec_json(spec)
    assert doc["headline"] == "Hi"
    assert doc["text"] == "Body copy here."
    assert source == "inline:json"


def test_rejects_s3_graph() -> None:
    spec = json.dumps(
        {
            "name": "s",
            "nodes": [{"id": "s3", "type": "S3Input", "params": {"bucket": "b"}}],
            "edges": [],
        }
    )
    with pytest.raises(ValueError, match="S3Input"):
        build_single_item_input_from_graph_spec_json(spec)


def test_rejects_empty_text() -> None:
    spec = json.dumps(
        {
            "name": "t",
            "nodes": [{"id": "a", "type": "TextInput", "params": {"text": "  "}}],
            "edges": [],
        }
    )
    with pytest.raises(ValueError, match="non-empty text"):
        build_single_item_input_from_graph_spec_json(spec)


def test_rejects_multiple_ingress() -> None:
    spec = json.dumps(
        {
            "name": "t",
            "nodes": [
                {"id": "a", "type": "TextInput", "params": {"text": "a"}},
                {"id": "b", "type": "JSONInput", "params": {"text": "b"}},
            ],
            "edges": [],
        }
    )
    with pytest.raises(ValueError, match="exactly one"):
        build_single_item_input_from_graph_spec_json(spec)
