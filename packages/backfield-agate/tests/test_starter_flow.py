"""Starter flow graph spec sanity checks."""

from agate_runtime import GraphSpec, starter_geocode_flow_graph_spec


def test_starter_geocode_flow_graph_spec_round_trip() -> None:
    spec = starter_geocode_flow_graph_spec()
    raw = spec.model_dump(mode="json")
    again = GraphSpec.model_validate(raw)
    assert again.name == "starter_flow"
    assert len(again.nodes) == 4
    assert len(again.edges) == 3
    assert {n.type for n in again.nodes} == {
        "TextInput",
        "PlaceExtract",
        "GeocodeAgent",
        "DBOutput",
    }


def test_starter_flow_positions_match_bootstrapped_canonical() -> None:
    """Positions match the Starter flow graph seeded by local bootstrap (exported UI layout)."""
    spec = starter_geocode_flow_graph_spec()
    by_id = {n.id: n.position for n in spec.nodes}
    assert by_id["n1"] == {"x": 0.0, "y": 0.0}
    assert by_id["n2"] == {"x": 337.487868852459, "y": 46.08393442622952}
    assert by_id["n3"] == {"x": 596.3311475409837, "y": 16.26491803278691}
    assert by_id["n5"] == {"x": 865.9777049180329, "y": 46.08393442622952}
