"""Starter flow graph spec sanity checks."""

from backfield_core import GraphSpec, starter_geocode_flow_graph_spec


def test_starter_geocode_flow_graph_spec_round_trip() -> None:
    spec = starter_geocode_flow_graph_spec()
    raw = spec.model_dump(mode="json")
    again = GraphSpec.model_validate(raw)
    assert again.name == "starter_geocode_flow"
    assert len(again.nodes) == 4
    assert len(again.edges) == 3
    assert {n.type for n in again.nodes} == {"TextInput", "PlaceExtract", "GeocodeAgent", "Output"}
