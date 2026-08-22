"""Tests for multi-document JSONInput batch detection."""

from __future__ import annotations

import json

from agate_runtime.json_input_batch import (
    graph_spec_json_contains_json_input_batch,
    json_input_batch_documents_from_spec,
)
from agate_runtime.types import GraphSpec


def test_graph_spec_json_contains_json_input_batch() -> None:
    multi = json.dumps(
        {
            "name": "m",
            "nodes": [
                {
                    "id": "j",
                    "type": "JSONInput",
                    "params": {
                        "documents": [
                            {"text": "a", "source_file": "a.json"},
                            {"text": "b", "source_file": "b.json"},
                        ]
                    },
                }
            ],
            "edges": [],
        }
    )
    single = json.dumps(
        {
            "name": "s",
            "nodes": [{"id": "j", "type": "JSONInput", "params": {"text": "only"}}],
            "edges": [],
        }
    )
    assert graph_spec_json_contains_json_input_batch(multi) is True
    assert graph_spec_json_contains_json_input_batch(single) is False


def test_json_input_batch_documents_from_spec() -> None:
    spec = GraphSpec.model_validate(
        {
            "name": "m",
            "nodes": [
                {
                    "id": "j",
                    "type": "JSONInput",
                    "params": {
                        "documents": [
                            {"text": " Alpha ", "source_file": "a.json", "headline": "A"},
                            {"text": "Beta", "source_file": "b.json"},
                        ]
                    },
                }
            ],
            "edges": [],
        }
    )
    docs = json_input_batch_documents_from_spec(spec)
    assert [name for name, _ in docs] == ["a.json", "b.json"]
    assert docs[0][1]["text"] == "Alpha"
    assert docs[0][1]["headline"] == "A"
