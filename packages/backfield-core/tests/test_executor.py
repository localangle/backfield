"""Unit tests for graph execution."""

from unittest.mock import patch

import pytest
from backfield_core import Edge, GraphSpec, NodeConfig, execute_graph
from backfield_core.executor import GraphExecutionError


def test_text_to_place_extract():
    spec = GraphSpec(
        name="t",
        nodes=[
            NodeConfig(id="a", type="TextInput", params={"text": "News from Chicago, IL today."}),
            NodeConfig(id="b", type="PlaceExtract", params={}),
        ],
        edges=[
            Edge(source="a", target="b", sourceHandle="text", targetHandle="text"),
        ],
    )
    out = execute_graph(spec)
    assert "Chicago" in out["b"]["locations"][0]["location"]


def test_unknown_node_type():
    spec = GraphSpec(
        name="x",
        nodes=[NodeConfig(id="z", type="NoSuchNode", params={})],
        edges=[],
    )
    with pytest.raises(GraphExecutionError, match="Unknown"):
        execute_graph(spec)


def test_four_node_pipeline_mock_geocode():
    spec = GraphSpec(
        name="pipeline",
        nodes=[
            NodeConfig(id="n1", type="TextInput", params={"text": "Meetings in Austin, TX."}),
            NodeConfig(id="n2", type="PlaceExtract", params={}),
            NodeConfig(id="n3", type="GeocodeAgent", params={}),
            NodeConfig(id="n4", type="Output", params={}),
        ],
        edges=[
            Edge(source="n1", target="n2", sourceHandle="text", targetHandle="text"),
            Edge(source="n2", target="n3", sourceHandle="locations", targetHandle="locations"),
            Edge(source="n3", target="n4", sourceHandle="locations", targetHandle="data"),
        ],
    )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"lat": 30.27, "lon": -97.74, "label": "Austin, TX"}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def post(self, url, json=None, headers=None):
            assert "geocode" in url
            return FakeResponse()

    with patch("backfield_core.nodes.geocode_agent.httpx.Client", FakeClient):
        out = execute_graph(spec)

    consolidated = out["n4"]["consolidated"]
    assert isinstance(consolidated, list)
    assert consolidated[0]["geocode"]["label"] == "Austin, TX"
