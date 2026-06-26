"""Execute an Agate graph synchronously or with predecessor-ready parallel scheduling."""

from __future__ import annotations

import asyncio
import os
import re
import time
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from typing import Any

from agate_runtime.context import AgateEnvContext
from agate_runtime.node_output_contract import (
    project_gathered_branch_refs,
    project_node_contribution,
)
from agate_runtime.nodes import NODE_RUNNERS
from agate_runtime.runners import ASYNC_NODE_RUNNERS, default_context
from agate_runtime.types import Edge, GraphSpec, NodeConfig

NodeRunner = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
AsyncNodeRunner = Callable[
    [dict[str, Any], dict[str, Any], AgateEnvContext],
    Any,
]
AfterEachNodeHook = Callable[[str, str, float], None]

# Default per-async-node wall budget (seconds). Sync nodes rely on Celery + DB timeouts.
_DEFAULT_ASYNC_NODE_TIMEOUT_S = 600.0


def _async_node_timeout_s() -> float | None:
    raw = os.environ.get("AGATE_NODE_TIMEOUT_S", str(int(_DEFAULT_ASYNC_NODE_TIMEOUT_S))).strip()
    if raw.lower() in ("", "0", "none", "off", "false"):
        return None
    try:
        return max(1.0, float(raw))
    except ValueError:
        return _DEFAULT_ASYNC_NODE_TIMEOUT_S

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


def _parallel_levels_enabled() -> bool:
    return os.environ.get("BACKFIELD_PARALLEL_GRAPH_LEVELS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


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


_INPUT_NODE_TYPES = frozenset({"TextInput", "JSONInput", "S3Input"})


def build_execution_levels(spec: GraphSpec) -> list[list[str]]:
    """Group node ids by graph depth (legacy level-barrier helper)."""
    sorted_ids = _topo_order(spec)
    node_ids = {n.id for n in spec.nodes}
    depths: dict[str, int] = {}
    for node_id in sorted_ids:
        max_input_depth = -1
        for edge in spec.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                continue
            if edge.target == node_id and edge.source in depths:
                max_input_depth = max(max_input_depth, depths[edge.source])
        depths[node_id] = max_input_depth + 1
    levels_dict: dict[int, list[str]] = defaultdict(list)
    for node_id, depth in depths.items():
        levels_dict[depth].append(node_id)
    return [levels_dict[i] for i in sorted(levels_dict.keys())]


def _direct_upstream_ids(target_id: str, edges: list[Edge], node_ids: set[str]) -> frozenset[str]:
    return frozenset(
        edge.source
        for edge in edges
        if edge.target == target_id and edge.source in node_ids
    )


def _all_other_nodes_complete(
    exclude_id: str,
    *,
    by_id: dict[str, NodeConfig],
    completed_ids: set[str],
) -> bool:
    required = {
        node.id
        for node in by_id.values()
        if node.id != exclude_id and node.type != "ArraySplitter"
    }
    return required <= completed_ids


def _transitive_downstream_ids(
    source_id: str,
    edges: list[Edge],
    node_ids: set[str],
) -> frozenset[str]:
    downstream: set[str] = set()
    queue: deque[str] = deque(
        edge.target for edge in edges if edge.source == source_id and edge.target in node_ids
    )
    while queue:
        current = queue.popleft()
        if current in downstream:
            continue
        downstream.add(current)
        queue.extend(
            edge.target
            for edge in edges
            if edge.source == current and edge.target in node_ids and edge.target not in downstream
        )
    return frozenset(downstream)


def _sync_barrier_prerequisite_ids(
    node_id: str,
    *,
    by_id: dict[str, NodeConfig],
    edges: list[Edge],
    node_ids: set[str],
) -> frozenset[str]:
    """Nodes that must finish before Gather runs (every node except downstream branches)."""
    downstream = _transitive_downstream_ids(node_id, edges, node_ids)
    return frozenset(
        nid
        for nid in node_ids
        if nid != node_id
        and nid not in downstream
        and by_id[nid].type != "ArraySplitter"
    )


def _node_is_ready(
    node: NodeConfig,
    *,
    completed_ids: set[str],
    by_id: dict[str, NodeConfig],
    edges: list[Edge],
    node_ids: set[str],
) -> bool:
    if node.type in ("Output", "Gather"):
        required = _sync_barrier_prerequisite_ids(
            node.id,
            by_id=by_id,
            edges=edges,
            node_ids=node_ids,
        )
        return required <= completed_ids
    upstream = _direct_upstream_ids(node.id, edges, node_ids)
    if not upstream and node.type in _INPUT_NODE_TYPES:
        return True
    return upstream <= completed_ids


def _all_namespaced_node_outputs(
    node_outputs: dict[str, dict[str, Any]],
    by_id: dict[str, NodeConfig],
) -> dict[str, Any]:
    """One namespace key per completed node (used by DBOutput consolidation)."""
    state: dict[str, Any] = {}
    for source_id, output in node_outputs.items():
        source_node = by_id.get(source_id)
        if source_node and source_node.type == "ArraySplitter":
            continue
        state[source_id] = dict(output)
    return state


def _namespaced_upstream_inputs(
    target_id: str,
    edges: list[Edge],
    node_outputs: dict[str, dict[str, Any]],
    by_id: dict[str, NodeConfig],
) -> dict[str, Any]:
    """One namespace key per direct upstream node id."""
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


def _namespaced_barrier_inputs(
    node_id: str,
    *,
    by_id: dict[str, NodeConfig],
    edges: list[Edge],
    node_outputs: dict[str, dict[str, Any]],
    node_ids: set[str],
) -> dict[str, Any]:
    required = _sync_barrier_prerequisite_ids(
        node_id,
        by_id=by_id,
        edges=edges,
        node_ids=node_ids,
    )
    state: dict[str, Any] = {}
    for source_id in sorted(required):
        if source_id not in node_outputs:
            continue
        source_node = by_id.get(source_id)
        if source_node and source_node.type == "ArraySplitter":
            continue
        state[source_id] = dict(node_outputs[source_id])
    return state


def _inputs_for_node(
    node: NodeConfig,
    *,
    edges: list[Edge],
    node_outputs: dict[str, dict[str, Any]],
    by_id: dict[str, NodeConfig],
) -> dict[str, Any]:
    node_ids = set(by_id)
    if node.type == "Output":
        return _merged_outputs_for_output(node_outputs, by_id)
    if node.type in ("DBOutput", "S3Output"):
        return _all_namespaced_node_outputs(node_outputs, by_id)
    if node.type == "Gather":
        return _namespaced_barrier_inputs(
            node.id,
            by_id=by_id,
            edges=edges,
            node_outputs=node_outputs,
            node_ids=node_ids,
        )
    return _namespaced_upstream_inputs(node.id, edges, node_outputs, by_id)


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
        raw_output = node_outputs[node_id]
        node_type = by_id[node_id].type
        if node_type == "Gather" and isinstance(raw_output, dict):
            gathered = raw_output.get("gathered")
            if isinstance(gathered, dict):
                out[public_key] = {
                    "gathered": project_gathered_branch_refs(
                        gathered,
                        source_id_to_public=id_to_public,
                        execution_order=order,
                    )
                }
                continue
        out[public_key] = project_node_contribution(node_type, raw_output)
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


def _run_sync_node(
    node: NodeConfig,
    inputs: dict[str, Any],
    runners: Mapping[str, NodeRunner],
    before_each_node: Callable[[str, str], None] | None,
    after_each_node: AfterEachNodeHook | None,
) -> dict[str, Any]:
    runner = runners.get(node.type)
    if not runner:
        raise GraphExecutionError(f"Unknown node type: {node.type}")
    if before_each_node is not None:
        before_each_node(node.id, node.type)
    t0 = time.perf_counter()
    try:
        result = runner(node.params, inputs)
    except Exception as exc:
        raise GraphExecutionError(f"Node {node.id} ({node.type}) failed: {exc}") from exc
    finally:
        if after_each_node is not None:
            after_each_node(node.id, node.type, time.perf_counter() - t0)
    if not isinstance(result, dict):
        raise GraphExecutionError(f"Node {node.id} returned non-dict: {type(result)}")
    return result


async def _run_node_async(
    node: NodeConfig,
    inputs: dict[str, Any],
    runners: Mapping[str, NodeRunner],
    *,
    before_each_node: Callable[[str, str], None] | None,
    after_each_node: AfterEachNodeHook | None,
    ctx: AgateEnvContext,
    async_runners: Mapping[str, AsyncNodeRunner],
) -> tuple[str, dict[str, Any]]:
    if before_each_node is not None:
        before_each_node(node.id, node.type)
    t0 = time.perf_counter()
    node_timeout_s = _async_node_timeout_s()
    try:
        async def _execute() -> dict[str, Any]:
            async_runner = async_runners.get(node.type)
            if async_runner is not None:
                result = await async_runner(node.params, inputs, ctx)
            else:
                sync_runner = runners.get(node.type)
                if sync_runner is None:
                    raise GraphExecutionError(f"Unknown node type: {node.type}")
                result = await asyncio.to_thread(sync_runner, node.params, inputs)
            if not isinstance(result, dict):
                raise GraphExecutionError(f"Node {node.id} returned non-dict: {type(result)}")
            return result

        if node_timeout_s is not None:
            result = await asyncio.wait_for(_execute(), timeout=node_timeout_s)
        else:
            result = await _execute()
    except TimeoutError as exc:
        raise GraphExecutionError(
            f"Node {node.id} ({node.type}) exceeded {node_timeout_s:.0f}s wall-clock limit"
        ) from exc
    except GraphExecutionError:
        raise
    except Exception as exc:
        raise GraphExecutionError(f"Node {node.id} ({node.type}) failed: {exc}") from exc
    finally:
        if after_each_node is not None:
            after_each_node(node.id, node.type, time.perf_counter() - t0)
    return node.id, result


async def _execute_level_async(
    level_nodes: list[NodeConfig],
    level_inputs: dict[str, dict[str, Any]],
    runners: Mapping[str, NodeRunner],
    *,
    before_each_node: Callable[[str, str], None] | None,
    after_each_node: AfterEachNodeHook | None,
    ctx: AgateEnvContext,
    async_runners: Mapping[str, AsyncNodeRunner],
) -> dict[str, dict[str, Any]]:
    pairs = await asyncio.gather(
        *[
            _run_node_async(
                node,
                level_inputs[node.id],
                runners,
                before_each_node=before_each_node,
                after_each_node=after_each_node,
                ctx=ctx,
                async_runners=async_runners,
            )
            for node in level_nodes
        ]
    )
    return dict(pairs)


def _execute_graph_sequential(
    spec: GraphSpec,
    runners: Mapping[str, NodeRunner],
    *,
    before_each_node: Callable[[str, str], None] | None,
    after_each_node: AfterEachNodeHook | None = None,
) -> dict[str, Any]:
    by_id = {node.id: node for node in spec.nodes}
    order = _topo_order(spec)
    node_ids = set(by_id)
    node_outputs: dict[str, dict[str, Any]] = {}
    completed_ids: set[str] = set()
    pending = set(by_id)

    while pending:
        ready = [
            by_id[node_id]
            for node_id in pending
            if _node_is_ready(
                by_id[node_id],
                completed_ids=completed_ids,
                by_id=by_id,
                edges=spec.edges,
                node_ids=node_ids,
            )
        ]
        if not ready:
            raise GraphExecutionError("Deadlock: no nodes ready to execute")
        for node in ready:
            pending.discard(node.id)
            inputs = _inputs_for_node(
                node, edges=spec.edges, node_outputs=node_outputs, by_id=by_id
            )
            node_outputs[node.id] = _run_sync_node(
                node, inputs, runners, before_each_node, after_each_node
            )
            completed_ids.add(node.id)

    return _remap_outputs_for_json(by_id, order, node_outputs)


def _execute_graph_parallel_levels(
    spec: GraphSpec,
    runners: Mapping[str, NodeRunner],
    *,
    before_each_node: Callable[[str, str], None] | None,
    after_each_node: AfterEachNodeHook | None = None,
    async_runners: Mapping[str, AsyncNodeRunner],
) -> dict[str, Any]:
    by_id = {node.id: node for node in spec.nodes}
    order = _topo_order(spec)
    node_outputs: dict[str, dict[str, Any]] = {}
    ctx = default_context()

    for level_ids in build_execution_levels(spec):
        level_nodes = [by_id[node_id] for node_id in level_ids]
        if len(level_nodes) == 1:
            node = level_nodes[0]
            inputs = _inputs_for_node(
                node, edges=spec.edges, node_outputs=node_outputs, by_id=by_id
            )
            node_outputs[node.id] = _run_sync_node(
                node, inputs, runners, before_each_node, after_each_node
            )
            continue

        level_inputs = {
            node.id: _inputs_for_node(
                node, edges=spec.edges, node_outputs=node_outputs, by_id=by_id
            )
            for node in level_nodes
        }
        level_results = asyncio.run(
            _execute_level_async(
                level_nodes,
                level_inputs,
                runners,
                before_each_node=before_each_node,
                after_each_node=after_each_node,
                ctx=ctx,
                async_runners=async_runners,
            )
        )
        node_outputs.update(level_results)

    return _remap_outputs_for_json(by_id, order, node_outputs)


async def _execute_graph_ready_parallel_async(
    spec: GraphSpec,
    runners: Mapping[str, NodeRunner],
    *,
    before_each_node: Callable[[str, str], None] | None,
    after_each_node: AfterEachNodeHook | None = None,
    async_runners: Mapping[str, AsyncNodeRunner],
) -> dict[str, Any]:
    by_id = {node.id: node for node in spec.nodes}
    order = _topo_order(spec)
    node_ids = set(by_id)
    pending_ids = set(by_id)
    completed_ids: set[str] = set()
    node_outputs: dict[str, dict[str, Any]] = {}
    in_flight: dict[str, asyncio.Task[tuple[str, dict[str, Any]]]] = {}
    ctx = default_context()

    def _ready_nodes() -> list[NodeConfig]:
        return [
            by_id[node_id]
            for node_id in pending_ids
            if _node_is_ready(
                by_id[node_id],
                completed_ids=completed_ids,
                by_id=by_id,
                edges=spec.edges,
                node_ids=node_ids,
            )
        ]

    def _launch_ready() -> None:
        for node in _ready_nodes():
            pending_ids.discard(node.id)
            inputs = _inputs_for_node(
                node, edges=spec.edges, node_outputs=node_outputs, by_id=by_id
            )
            in_flight[node.id] = asyncio.create_task(
                _run_node_async(
                    node,
                    inputs,
                    runners,
                    before_each_node=before_each_node,
                    after_each_node=after_each_node,
                    ctx=ctx,
                    async_runners=async_runners,
                )
            )

    _launch_ready()
    while in_flight:
        done, _pending = await asyncio.wait(
            in_flight.values(),
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            node_id, result = task.result()
            node_outputs[node_id] = result
            completed_ids.add(node_id)
            del in_flight[node_id]
        _launch_ready()
        if not in_flight and pending_ids:
            raise GraphExecutionError("Deadlock: no nodes ready to execute")

    return _remap_outputs_for_json(by_id, order, node_outputs)


def _execute_graph_ready_parallel(
    spec: GraphSpec,
    runners: Mapping[str, NodeRunner],
    *,
    before_each_node: Callable[[str, str], None] | None,
    after_each_node: AfterEachNodeHook | None = None,
    async_runners: Mapping[str, AsyncNodeRunner],
) -> dict[str, Any]:
    return asyncio.run(
        _execute_graph_ready_parallel_async(
            spec,
            runners,
            before_each_node=before_each_node,
            after_each_node=after_each_node,
            async_runners=async_runners,
        )
    )


def execute_graph(
    spec: GraphSpec,
    node_runners: Mapping[str, NodeRunner] | None = None,
    *,
    before_each_node: Callable[[str, str], None] | None = None,
    after_each_node: AfterEachNodeHook | None = None,
) -> dict[str, Any]:
    """
    Run all nodes in dependency order.

    When ``BACKFIELD_PARALLEL_GRAPH_LEVELS`` is ``1``/``true``/``yes``, each node runs
    as soon as its readiness rules are satisfied (direct upstream for most nodes;
    JSON ``Output`` and ``Gather`` wait for every non-downstream node in the graph
    (``Gather`` returns namespaced upstream outputs; ``Output`` shallow-merges them);
    ``DBOutput`` waits for direct wired upstream only but consolidates **all** completed
    node outputs for persistence). Ready nodes in a batch run
    concurrently via ``asyncio.gather``.

    ``before_each_node``, when provided, is invoked as ``(node_id, node_type)`` immediately
    before each node's runner (used by the worker for LLM attempt attribution).
    ``after_each_node``, when provided, is invoked as ``(node_id, node_type, elapsed_s)``
    after each node's runner completes (wall-clock including non-LLM work).

    Returns a JSON-serializable dict whose top-level keys are stable snake_case strings
    per node (for example ``text_input``, ``json_output``, ``stylebook_output``), not
    internal React Flow ids. Execution still uses internal ids for wiring; downstream
    runners receive namespaced inputs keyed by id.
    """
    runners = NODE_RUNNERS if node_runners is None else dict(NODE_RUNNERS) | dict(node_runners)

    if _parallel_levels_enabled():
        return _execute_graph_ready_parallel(
            spec,
            runners,
            before_each_node=before_each_node,
            after_each_node=after_each_node,
            async_runners=ASYNC_NODE_RUNNERS,
        )
    return _execute_graph_sequential(
        spec, runners, before_each_node=before_each_node, after_each_node=after_each_node
    )
