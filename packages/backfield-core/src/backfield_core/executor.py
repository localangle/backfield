"""Execute an Agate graph synchronously."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from typing import Any

from backfield_core.nodes import NODE_RUNNERS
from backfield_core.types import Edge, GraphSpec, NodeConfig

NodeRunner = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


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
    Run all nodes in dependency order. Returns mapping node_id -> output dict.
    Raises GraphExecutionError on unknown node type or wiring errors.
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

        if node.type in {"Output", "DBOutput"}:
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

    return node_outputs
