"""Execute an Agate graph synchronously."""

from __future__ import annotations

import re
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from typing import Any

from backfield_agate.nodes import NODE_RUNNERS
from backfield_agate.types import Edge, GraphSpec, NodeConfig

NodeRunner = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]

# Stable JSON keys for run results: snake_case from node type, with palette aliases where needed.
_NODE_TYPE_OUTPUT_SLUGS: dict[str, str] = {
    "Output": "json_output",
    "DBOutput": "stylebook_output",
}


def _node_type_to_output_slug(node_type: str) -> str:
    if node_type in _NODE_TYPE_OUTPUT_SLUGS:
        return _NODE_TYPE_OUTPUT_SLUGS[node_type]
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", node_type)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    return s2.lower()


class GraphExecutionError(Exception):
    pass


def _topo_order(spec: GraphSpec) -> list[str]:
    node_ids = {n.id for n in spec.nodes}
    in_degree: dict[str, int] = {n.id: 0 for n in spec.nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)

    for edge in spec.edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            continue
        in_degree[edge.target] += 1
        outgoing[edge.source].append(edge.target)

    queue: deque[str] = deque(node_id for node_id, degree in in_degree.items() if degree == 0)
    order: list[str] = []

    while queue:
        current = queue.popleft()
        order.append(current)
        for downstream in outgoing[current]:
            in_degree[downstream] -= 1
            if in_degree[downstream] == 0:
                queue.append(downstream)

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
    for edge in edges:
        if edge.target != target_id:
            continue
        source_id = edge.source
        if source_id not in node_outputs:
            raise GraphExecutionError(f"Missing outputs for source node {source_id}")
        source_node = by_id.get(source_id)
        if source_node and source_node.type == "ArraySplitter":
            continue
        state[source_id] = dict(node_outputs[source_id])
    return state


def _public_node_output_keys(
    by_id: dict[str, NodeConfig],
    order: list[str],
) -> dict[str, str]:
    """Map internal node id -> unique top-level JSON key (execution order for disambiguation)."""
    per_base_count: dict[str, int] = defaultdict(int)
    id_to_public: dict[str, str] = {}
    used_public: set[str] = set()

    for node_id in order:
        node = by_id[node_id]
        base = _node_type_to_output_slug(node.type)
        per_base_count[base] += 1
        if per_base_count[base] == 1:
            public = base
        else:
            public = f"{base}_{node_id}"
        if public in used_public:
            public = node_id
        used_public.add(public)
        id_to_public[node_id] = public

    return id_to_public


def _remap_outputs_for_json(
    by_id: dict[str, NodeConfig],
    order: list[str],
    node_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Top-level keys are snake_case slugs from node types (see ``_NODE_TYPE_OUTPUT_SLUGS``)."""
    id_to_public = _public_node_output_keys(by_id, order)
    out: dict[str, Any] = {}
    for node_id in order:
        public_key = id_to_public[node_id]
        out[public_key] = node_outputs[node_id]
    return out


def _merged_outputs_for_output(
    node_outputs: dict[str, dict[str, Any]],
    by_id: dict[str, NodeConfig],
) -> dict[str, Any]:
    """Match agate Output node: shallow-merge all completed node outputs."""
    merged: dict[str, Any] = {}
    for source_id, output in node_outputs.items():
        source_node = by_id.get(source_id)
        if source_node and source_node.type == "ArraySplitter":
            continue
        merged.update(dict(output))
    return merged


def execute_graph(
    spec: GraphSpec,
    node_runners: Mapping[str, NodeRunner] | None = None,
    *,
    before_each_node: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """
    Run all nodes in dependency order.

    ``before_each_node``, when provided, is invoked as ``(node_id, node_type)`` immediately
    before each node's runner (used by the worker for LLM attempt attribution).

    Returns a JSON-serializable dict whose top-level keys are stable snake_case strings
    per node (for example ``text_input``, ``json_output``, ``stylebook_output``), not
    internal React Flow ids. Execution still uses internal ids for wiring; downstream
    runners receive namespaced inputs keyed by id.
    """
    by_id = {node.id: node for node in spec.nodes}
    order = _topo_order(spec)
    node_outputs: dict[str, dict[str, Any]] = {}

    runners = NODE_RUNNERS if node_runners is None else dict(NODE_RUNNERS) | dict(node_runners)

    for node_id in order:
        node = by_id[node_id]
        runner = runners.get(node.type)
        if not runner:
            raise GraphExecutionError(f"Unknown node type: {node.type}")

        if node.type == "Output":
            inputs = _merged_outputs_for_output(node_outputs, by_id)
        else:
            inputs = _namespaced_upstream_inputs(node_id, spec.edges, node_outputs, by_id)

        if before_each_node is not None:
            before_each_node(node_id, node.type)

        try:
            result = runner(node.params, inputs)
        except Exception as exc:
            raise GraphExecutionError(f"Node {node_id} ({node.type}) failed: {exc}") from exc

        if not isinstance(result, dict):
            raise GraphExecutionError(f"Node {node_id} returned non-dict: {type(result)}")
        node_outputs[node_id] = result

    return _remap_outputs_for_json(by_id, order, node_outputs)
