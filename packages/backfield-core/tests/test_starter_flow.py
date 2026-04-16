"""Starter flow graph spec sanity checks."""

from backfield_core import GraphSpec, starter_geocode_flow_graph_spec


def test_starter_geocode_flow_graph_spec_round_trip() -> None:
    spec = starter_geocode_flow_graph_spec()
    raw = spec.model_dump(mode="json")
    again = GraphSpec.model_validate(raw)
    assert again.name == "starter_geocode_flow"
    assert len(again.nodes) == 5
    assert len(again.edges) == 4
    assert {n.type for n in again.nodes} == {
        "TextInput",
        "PlaceExtract",
        "GeocodeAgent",
        "Output",
        "DBOutput",
    }


def test_starter_flow_positions_match_db_migration_002() -> None:
    """Keep in sync with packages/backfield-db/alembic/versions/002_starter_flow_layout.py."""
    spec = starter_geocode_flow_graph_spec()
    by_id = {n.id: n.position for n in spec.nodes}
    assert by_id["n1"] == {"x": 0.0, "y": 0.0}
    assert by_id["n2"] == {"x": 328.0, "y": 0.0}
    assert by_id["n3"] == {"x": 576.0, "y": 0.0}
    assert by_id["n4"] == {"x": 824.0, "y": 0.0}
    assert by_id["n5"] == {"x": 1072.0, "y": 0.0}
