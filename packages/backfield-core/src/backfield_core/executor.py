"""Execute an Agate graph synchronously."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from backfield_core.nodes import NODE_RUNNERS
from backfield_core.types import GraphSpec


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


def _pick_output_port(outputs: dict[str, Any], handle: str | None) -> Any:
    if handle and handle in outputs:
        return outputs[handle]
    if len(outputs) == 1:
        return next(iter(outputs.values()))
    if handle is None and outputs:
        return next(iter(outputs.values()))
    raise GraphExecutionError(f"Cannot resolve output port {handle!r} from {outputs!r}")


def execute_graph(spec: GraphSpec) -> dict[str, Any]:
    """
    Run all nodes in dependency order. Returns mapping node_id -> output dict.
    Raises GraphExecutionError on unknown node type or wiring errors.
    """
    by_id = {n.id: n for n in spec.nodes}
    order = _topo_order(spec)
    node_outputs: dict[str, dict[str, Any]] = {}

    # incoming edges per target
    incoming: dict[str, list[tuple[str, str | None, str | None]]] = defaultdict(list)
    for e in spec.edges:
        incoming[e.target].append((e.source, e.sourceHandle, e.targetHandle))

    for nid in order:
        node = by_id[nid]
        runner = NODE_RUNNERS.get(node.type)
        if not runner:
            raise GraphExecutionError(f"Unknown node type: {node.type}")

        inputs: dict[str, Any] = {}
        for src, src_handle, tgt_handle in incoming[nid]:
            src_out = node_outputs.get(src)
            if not src_out:
                raise GraphExecutionError(f"Missing outputs for source node {src}")
            val = _pick_output_port(src_out, src_handle)
            port = tgt_handle or src_handle or "data"
            inputs[port] = val

        try:
            result = runner(node.params, inputs)
        except Exception as e:
            raise GraphExecutionError(f"Node {nid} ({node.type}) failed: {e}") from e

        if not isinstance(result, dict):
            raise GraphExecutionError(f"Node {nid} returned non-dict: {type(result)}")
        node_outputs[nid] = result

    return node_outputs
