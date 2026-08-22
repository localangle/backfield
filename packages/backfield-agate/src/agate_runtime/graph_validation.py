"""Graph invariants that go beyond GraphSpec structural validation."""

from __future__ import annotations

from collections import defaultdict, deque

from agate_runtime.types import GraphSpec

INPUT_BOOKEND_TYPES = frozenset({"TextInput", "JSONInput", "S3Input"})
DOCUMENT_CHUNKER_TYPE = "DocumentChunker"

# Mirrors metadata ``requiredUpstreamNodes`` (at least one type must appear in ancestry).
REQUIRED_UPSTREAM_BY_TYPE: dict[str, frozenset[str]] = {
    "GeocodeAgent": frozenset({"PlaceExtract"}),
}


class GraphInvariantError(ValueError):
    """Raised when a graph violates product placement rules."""


def validate_document_chunker_placement(spec: GraphSpec) -> None:
    """Enforce at most one input-adjacent Document Chunker with no bypass branches."""
    chunkers = [node for node in spec.nodes if node.type == DOCUMENT_CHUNKER_TYPE]
    if not chunkers:
        return
    if len(chunkers) > 1:
        raise GraphInvariantError(
            "A flow can include only one Document Chunker."
        )

    chunker = chunkers[0]
    node_ids = {node.id for node in spec.nodes}
    by_id = {node.id: node for node in spec.nodes}

    incoming = [
        edge
        for edge in spec.edges
        if edge.target == chunker.id and edge.source in node_ids
    ]
    if len(incoming) != 1:
        raise GraphInvariantError(
            "Document Chunker must connect directly from the content source "
            "(Text Input, JSON Input, or S3 Input)."
        )

    source = by_id.get(incoming[0].source)
    if source is None or source.type not in INPUT_BOOKEND_TYPES:
        raise GraphInvariantError(
            "Document Chunker must be placed directly after Text Input, JSON Input, or S3 Input."
        )

    # Every first-hop child of the input must be the chunker (no bypass branch).
    input_children = [
        edge.target
        for edge in spec.edges
        if edge.source == source.id and edge.target in node_ids
    ]
    if not input_children:
        raise GraphInvariantError(
            "Document Chunker must be connected from the content source."
        )
    if any(child_id != chunker.id for child_id in input_children):
        raise GraphInvariantError(
            "When a Document Chunker is present, every step after the content source "
            "must go through the Document Chunker."
        )


def _ancestor_types(spec: GraphSpec, node_id: str) -> set[str]:
    """Return node types reachable by walking incoming edges (excludes ``node_id`` itself)."""
    by_id = {node.id: node for node in spec.nodes}
    incoming: dict[str, list[str]] = defaultdict(list)
    for edge in spec.edges:
        if edge.source in by_id and edge.target in by_id:
            incoming[edge.target].append(edge.source)

    found: set[str] = set()
    queue: deque[str] = deque(incoming.get(node_id, []))
    seen: set[str] = set()
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        node = by_id.get(current)
        if node is None:
            continue
        found.add(node.type)
        queue.extend(incoming.get(current, []))
    return found


def validate_required_upstream_nodes(spec: GraphSpec) -> None:
    """Enforce metadata-style ``requiredUpstreamNodes`` via transitive ancestry."""
    for node in spec.nodes:
        required = REQUIRED_UPSTREAM_BY_TYPE.get(node.type)
        if not required:
            continue
        ancestors = _ancestor_types(spec, node.id)
        if ancestors.isdisjoint(required):
            if node.type == "GeocodeAgent":
                raise GraphInvariantError(
                    "Geocode Agent must follow Place Extract in the same branch."
                )
            needed = ", ".join(sorted(required))
            raise GraphInvariantError(
                f"{node.type} requires one of these earlier steps in the same branch: {needed}."
            )


def validate_graph_invariants(spec: GraphSpec) -> None:
    """Run all product-level graph invariants."""
    validate_document_chunker_placement(spec)
    validate_required_upstream_nodes(spec)
    _assert_acyclic(spec)


def _assert_acyclic(spec: GraphSpec) -> None:
    node_ids = {node.id for node in spec.nodes}
    in_degree: dict[str, int] = {node.id: 0 for node in spec.nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in spec.edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            continue
        in_degree[edge.target] += 1
        outgoing[edge.source].append(edge.target)
    queue: deque[str] = deque(nid for nid, degree in in_degree.items() if degree == 0)
    seen = 0
    while queue:
        current = queue.popleft()
        seen += 1
        for nxt in outgoing[current]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
    if seen != len(spec.nodes):
        raise GraphInvariantError("Flow contains a cycle.")
