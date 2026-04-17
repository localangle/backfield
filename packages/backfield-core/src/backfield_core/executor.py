"""Execute an Agate graph synchronously."""

from __future__ import annotations

import re
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from typing import Any

from backfield_core.nodes import NODE_RUNNERS
from backfield_core.types import Edge, GraphSpec, NodeConfig

NodeRunner = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]

# Human-readable JSON keys for run results (aligned with Agate UI node metadata labels).
_NODE_TYPE_DISPLAY_NAMES: dict[str, str] = {
    "TextInput": "Text Input",
    "PlaceExtract": "Place Extract",
    "GeocodeAgent": "Geocode Agent",
    "Output": "JSON Output",
    "DBOutput": "DB Output",
}

_OUTPUT_KEY_INDEX = "__outputKeysByNodeId"


class GraphExecutionError(Exception):
    pass


def _topo_order(spec: GraphSpec) -> list[str]:
    node_ids = {n.id for n in spec.nodes}
    in_degree: dict[str, int] = {n.id: 0 for n in spec.nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)

    for e in spec.edges:
        if e.source not in node_ids or e.target not in node_ids:
            continue
        in_degree[e.target] += 1
        outgoing[e.source].append(e.target)

    queue: deque[str] = deque(nid for nid, d in in_degree.items() if d == 0)
    order: list[str] = []

    while queue:
        u = queue.popleft()
        order.append(u)
        for v in outgoing[u]:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    if len(order) != len(spec.nodes):
        raise GraphExecutionError("Cycle detected or invalid graph")

    return order


def _namespaced_upstream_inputs(
    target_id: str,
    edges: list[Edge],
    node_outputs: dict[str, dict[str, Any]],
    by_id: dict[str, NodeConfig],
) -> dict[str, Any]:
    """Match agate-ai-platform worker: one namespace key per direct upstream node id."""
    state: dict[str, Any] = {}
    for e in edges:
        if e.target != target_id:
            continue
        src = e.source
        if src not in node_outputs:
            raise GraphExecutionError(f"Missing outputs for source node {src}")
        src_node = by_id.get(src)
        if src_node and src_node.type == "ArraySplitter":
            continue
        state[src] = dict(node_outputs[src])
    return state


def _node_display_base_name(node: NodeConfig) -> str:
    """Display name for JSON keys from params or catalog, else prettified node type."""
    params = node.params if isinstance(node.params, dict) else {}
    for key in ("label", "name", "title"):
        val = params.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    if node.type in _NODE_TYPE_DISPLAY_NAMES:
        return _NODE_TYPE_DISPLAY_NAMES[node.type]
    return _prettify_node_type(node.type)


def _prettify_node_type(node_type: str) -> str:
    """Best-effort split CamelCase / PascalCase for unknown node types."""
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", node_type)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    return s.strip()


def _public_node_output_keys(
    by_id: dict[str, NodeConfig],
    order: list[str],
) -> dict[str, str]:
    """Map internal node id -> unique JSON object key (execution order for disambiguation)."""
    per_base_count: dict[str, int] = defaultdict(int)
    id_to_public: dict[str, str] = {}
    used_public: set[str] = set()

    for nid in order:
        node = by_id[nid]
        base = _node_display_base_name(node)
        per_base_count[base] += 1
        if per_base_count[base] == 1:
            public = base
        else:
            public = f"{base} ({nid})"
        if public in used_public:
            public = nid
        used_public.add(public)
        id_to_public[nid] = public

    return id_to_public


def _remap_outputs_for_json(
    by_id: dict[str, NodeConfig],
    order: list[str],
    node_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Human-readable top-level keys plus ``__outputKeysByNodeId`` (id -> key)."""
    id_to_public = _public_node_output_keys(by_id, order)
    out: dict[str, Any] = {}
    for nid in order:
        pub = id_to_public[nid]
        out[pub] = node_outputs[nid]
    out[_OUTPUT_KEY_INDEX] = id_to_public
    return out


def _merged_outputs_for_output(
    node_outputs: dict[str, dict[str, Any]],
    by_id: dict[str, NodeConfig],
) -> dict[str, Any]:
    """Match agate Output node: shallow-merge all completed node outputs."""
    merged: dict[str, Any] = {}
    for source_id, out in node_outputs.items():
        src_node = by_id.get(source_id)
        if src_node and src_node.type == "ArraySplitter":
            continue
        merged.update(dict(out))
    return merged


def execute_graph(
    spec: GraphSpec,
    node_runners: Mapping[str, NodeRunner] | None = None,
) -> dict[str, Any]:
    """
    Run all nodes in dependency order.

    Returns a JSON-serializable dict whose top-level keys are human-readable node labels
    (plus ``__outputKeysByNodeId`` mapping internal node ids to those keys). Execution still
    uses internal ids for wiring; downstream runners receive namespaced inputs keyed by id.
    """
    by_id = {n.id: n for n in spec.nodes}
    order = _topo_order(spec)
    node_outputs: dict[str, dict[str, Any]] = {}

    runners = NODE_RUNNERS if node_runners is None else dict(NODE_RUNNERS) | dict(node_runners)

    for nid in order:
        node = by_id[nid]
        runner = runners.get(node.type)
        if not runner:
            raise GraphExecutionError(f"Unknown node type: {node.type}")

        # Match agate-ai-platform worker `map_node_inputs`: only JSON `Output` deep-merges
        # all completed node outputs. `DBOutput` consolidates from wired upstream nodes only
        # (namespaced by source id), like other consumers — it does not require JSON Output.
        if node.type == "Output":
            inputs = _merged_outputs_for_output(node_outputs, by_id)
        else:
            inputs = _namespaced_upstream_inputs(nid, spec.edges, node_outputs, by_id)

        try:
            result = runner(node.params, inputs)
        except Exception as e:
            raise GraphExecutionError(f"Node {nid} ({node.type}) failed: {e}") from e

        if not isinstance(result, dict):
            raise GraphExecutionError(f"Node {nid} returned non-dict: {type(result)}")
        node_outputs[nid] = result

    return _remap_outputs_for_json(by_id, order, node_outputs)
