"""Detect and extract multi-document JSONInput batches (inline files on the node)."""

from __future__ import annotations

import json
from typing import Any

from agate_nodes.json_input.node import (
    JSON_INPUT_MAX_DOCUMENTS,
    documents_for_batch_execution,
    is_json_input_multi_document,
)

from agate_runtime.types import GraphSpec


def first_json_input_params(spec: GraphSpec) -> dict[str, Any]:
    for node in spec.nodes:
        if node.type == "JSONInput":
            return dict(node.params) if isinstance(node.params, dict) else {}
    raise ValueError("Graph has no JSONInput node.")


def graph_spec_json_contains_json_input_batch(spec_json: str) -> bool:
    """True when the graph's JSONInput holds two or more ``documents`` entries."""
    try:
        data = json.loads(spec_json)
    except json.JSONDecodeError:
        return False
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return False
    for node in nodes:
        if not isinstance(node, dict) or node.get("type") != "JSONInput":
            continue
        params = node.get("params")
        if isinstance(params, dict) and is_json_input_multi_document(params):
            return True
    return False


def json_input_batch_documents_from_spec(
    spec: GraphSpec,
    *,
    max_documents: int = JSON_INPUT_MAX_DOCUMENTS,
) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(source_file, normalized_doc)`` for each multi-file JSONInput document."""
    params = first_json_input_params(spec)
    if not is_json_input_multi_document(params):
        raise ValueError("JSONInput is not in multi-document batch mode.")
    return documents_for_batch_execution(params, max_documents=max_documents)
