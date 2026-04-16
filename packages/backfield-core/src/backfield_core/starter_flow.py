"""Canonical geocode starter graph.

Topology: TextInput → PlaceExtract → GeocodeAgent → JSON Output → DB Output.
"""

from __future__ import annotations

from backfield_core.types import Edge, GraphSpec, NodeConfig

# Stored graph name in agate_graph.name (UI + smoke lookup).
STARTER_FLOW_GRAPH_DISPLAY_NAME = "Starter flow"


def starter_geocode_flow_graph_spec() -> GraphSpec:
    """Same topology as the golden-path smoke flow (includes edge handles).

    Horizontal spacing matches Agate UI node card widths (TextInput ~280px, others ~200px)
    so nodes do not overlap when positions are interpreted as top-left in React Flow.
    """
    gap = 48
    # n1 TextInput w-[280px]; then 200px-wide nodes with a gap between each.
    w_text = 280.0
    w_card = 200.0
    x1 = 0.0
    x2 = x1 + w_text + gap
    x3 = x2 + w_card + gap
    x4 = x3 + w_card + gap
    x5 = x4 + w_card + gap
    y = 0.0
    return GraphSpec(
        name="starter_geocode_flow",
        nodes=[
            NodeConfig(
                id="n1",
                type="TextInput",
                params={"text": "We visited Chicago, IL and Austin, TX."},
                position={"x": x1, "y": y},
            ),
            NodeConfig(
                id="n2",
                type="PlaceExtract",
                params={},
                position={"x": x2, "y": y},
            ),
            NodeConfig(
                id="n3",
                type="GeocodeAgent",
                params={},
                position={"x": x3, "y": y},
            ),
            NodeConfig(
                id="n4",
                type="Output",
                params={},
                position={"x": x4, "y": y},
            ),
            NodeConfig(
                id="n5",
                type="DBOutput",
                params={},
                position={"x": x5, "y": y},
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
            Edge(
                source="n4",
                target="n5",
                sourceHandle="consolidated",
                targetHandle="data",
            ),
        ],
    )
