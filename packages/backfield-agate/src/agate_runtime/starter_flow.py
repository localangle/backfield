"""Canonical geocode starter graph.

Topology: TextInput → PlaceExtract → GeocodeAgent → Stylebook Output (DBOutput).
"""

from __future__ import annotations

from agate_runtime.types import Edge, GraphSpec, NodeConfig

# Stored graph name in agate_graph.name (UI + smoke lookup).
STARTER_FLOW_GRAPH_DISPLAY_NAME = "Starter flow"


def starter_geocode_flow_graph_spec() -> GraphSpec:
    """Golden-path starter: geocode then persist, with DBOutput wired directly from GeocodeAgent.

    Positions match the graph exported from Agate UI for this layout.
    """
    return GraphSpec(
        name="starter_flow",
        nodes=[
            NodeConfig(
                id="n1",
                type="TextInput",
                params={"text": "We visited Chicago, IL and Austin, TX."},
                position={"x": 0.0, "y": 0.0},
            ),
            NodeConfig(
                id="n2",
                type="PlaceExtract",
                params={},
                position={"x": 337.487868852459, "y": 46.08393442622952},
            ),
            NodeConfig(
                id="n3",
                type="GeocodeAgent",
                params={},
                position={"x": 596.3311475409837, "y": 16.26491803278691},
            ),
            NodeConfig(
                id="n5",
                type="DBOutput",
                params={
                    "stylebook_id": None,
                    "canonicalization_mode": "rules",
                    "auto_apply_canonicalization": True,
                    "adjudication_model": "gpt-5-nano",
                },
                position={"x": 865.9777049180329, "y": 46.08393442622952},
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
                target="n5",
                sourceHandle="locations",
                targetHandle="data",
            ),
        ],
    )
