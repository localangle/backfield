"""Canonical four-node geocode starter graph (TextInput through Output) for bootstrap and smoke."""

from __future__ import annotations

from backfield_core.types import Edge, GraphSpec, NodeConfig

# Stored graph name in agate_graph.name (UI + smoke lookup).
STARTER_FLOW_GRAPH_DISPLAY_NAME = "Starter flow"


def starter_geocode_flow_graph_spec() -> GraphSpec:
    """Same topology as the golden-path smoke flow (includes edge handles)."""
    return GraphSpec(
        name="starter_geocode_flow",
        nodes=[
            NodeConfig(
                id="n1",
                type="TextInput",
                params={"text": "We visited Chicago, IL and Austin, TX."},
                position={"x": 0, "y": 0},
            ),
            NodeConfig(
                id="n2",
                type="PlaceExtract",
                params={},
                position={"x": 220, "y": 0},
            ),
            NodeConfig(
                id="n3",
                type="GeocodeAgent",
                params={},
                position={"x": 440, "y": 0},
            ),
            NodeConfig(
                id="n4",
                type="Output",
                params={},
                position={"x": 660, "y": 0},
            ),
        ],
        edges=[
            Edge(source="n1", target="n2", sourceHandle="text", targetHandle="text"),
            Edge(
                source="n2",
                target="n3",
                sourceHandle="locations",
                targetHandle="locations",
            ),
            Edge(
                source="n3",
                target="n4",
                sourceHandle="locations",
                targetHandle="data",
            ),
        ],
    )
