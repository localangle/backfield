"""Tests for product-level graph invariants (Document Chunker placement)."""

from __future__ import annotations

import pytest
from agate_runtime.graph_validation import GraphInvariantError, validate_graph_invariants
from agate_runtime.types import Edge, GraphSpec, NodeConfig


def _spec(
    nodes: list[NodeConfig],
    edges: list[Edge],
) -> GraphSpec:
    return GraphSpec(name="test", nodes=nodes, edges=edges)


def test_validate_graph_invariants_allows_valid_document_chunker() -> None:
    spec = _spec(
        [
            NodeConfig(id="in", type="TextInput"),
            NodeConfig(id="chunk", type="DocumentChunker"),
            NodeConfig(id="pe", type="PlaceExtract"),
            NodeConfig(id="out", type="Output"),
        ],
        [
            Edge(source="in", target="chunk"),
            Edge(source="chunk", target="pe"),
            Edge(source="pe", target="out"),
        ],
    )
    validate_graph_invariants(spec)


def test_validate_graph_invariants_rejects_multiple_document_chunkers() -> None:
    spec = _spec(
        [
            NodeConfig(id="in", type="TextInput"),
            NodeConfig(id="c1", type="DocumentChunker"),
            NodeConfig(id="c2", type="DocumentChunker"),
            NodeConfig(id="out", type="Output"),
        ],
        [
            Edge(source="in", target="c1"),
            Edge(source="c1", target="c2"),
            Edge(source="c2", target="out"),
        ],
    )
    with pytest.raises(GraphInvariantError, match="only one Document Chunker"):
        validate_graph_invariants(spec)


def test_validate_graph_invariants_rejects_bypass_branch() -> None:
    spec = _spec(
        [
            NodeConfig(id="in", type="TextInput"),
            NodeConfig(id="chunk", type="DocumentChunker"),
            NodeConfig(id="pe", type="PlaceExtract"),
            NodeConfig(id="out", type="Output"),
        ],
        [
            Edge(source="in", target="chunk"),
            Edge(source="in", target="pe"),
            Edge(source="chunk", target="out"),
            Edge(source="pe", target="out"),
        ],
    )
    with pytest.raises(GraphInvariantError, match="every step after the content source"):
        validate_graph_invariants(spec)


def test_validate_graph_invariants_rejects_chunker_not_after_input() -> None:
    spec = _spec(
        [
            NodeConfig(id="in", type="TextInput"),
            NodeConfig(id="pe", type="PlaceExtract"),
            NodeConfig(id="chunk", type="DocumentChunker"),
            NodeConfig(id="out", type="Output"),
        ],
        [
            Edge(source="in", target="pe"),
            Edge(source="pe", target="chunk"),
            Edge(source="chunk", target="out"),
        ],
    )
    with pytest.raises(GraphInvariantError, match="directly after"):
        validate_graph_invariants(spec)


def test_validate_graph_invariants_rejects_cycles() -> None:
    spec = _spec(
        [
            NodeConfig(id="a", type="PlaceExtract"),
            NodeConfig(id="b", type="PlaceExtract"),
        ],
        [
            Edge(source="a", target="b"),
            Edge(source="b", target="a"),
        ],
    )
    with pytest.raises(GraphInvariantError, match="cycle"):
        validate_graph_invariants(spec)
