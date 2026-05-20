"""Extract one article payload from TextInput / JSONInput for ``agate_processed_item`` rows."""

from __future__ import annotations

from typing import Any

from agate_runtime.nodes.json_input import json_input_output_from_dict
from agate_runtime.s3_batch import graph_spec_json_contains_s3_input
from agate_runtime.types import GraphSpec, NodeConfig

_SINGLE_ITEM_INGRESS_TYPES: frozenset[str] = frozenset({"TextInput", "JSONInput"})


def _ingress_nodes(spec: GraphSpec) -> list[NodeConfig]:
    return [node for node in spec.nodes if node.type in _SINGLE_ITEM_INGRESS_TYPES]


def build_single_item_input_from_graph_spec_json(spec_json: str) -> tuple[dict[str, Any], str]:
    """Build ``input_json`` document and a stable ``source_file`` label for one-item runs.

    Raises ``ValueError`` when the graph is not eligible (S3 batch, missing ingress, etc.).
    """
    if graph_spec_json_contains_s3_input(spec_json):
        raise ValueError("Graphs with S3Input use batch setup, not single-item ingress.")

    spec = GraphSpec.model_validate_json(spec_json)
    ingress = _ingress_nodes(spec)
    if not ingress:
        raise ValueError(
            "Single-item runs require exactly one TextInput or JSONInput node in the graph."
        )
    if len(ingress) > 1:
        raise ValueError(
            "Single-item runs require exactly one TextInput or JSONInput node; "
            f"found {len(ingress)}."
        )

    node = ingress[0]
    if node.type == "TextInput":
        text = node.params.get("text") or ""
        if not str(text).strip():
            raise ValueError(
                "TextInput requires non-empty text before running the flow."
            )
        return {"text": str(text)}, "inline:text"

    if node.type == "JSONInput":
        params = dict(node.params) if isinstance(node.params, dict) else {}
        return json_input_output_from_dict(params), "inline:json"

    raise ValueError(f"Unsupported ingress node type: {node.type!r}")
