"""Unit tests for graph execution."""

import json
from unittest.mock import patch

import pytest
from backfield_core import Edge, GraphSpec, NodeConfig, execute_graph
from backfield_core.executor import GraphExecutionError


def _mock_place_extract_json(city: str, state_name: str, state_abbr: str) -> str:
    return json.dumps(
        {
            "locations": [
                {
                    "original_text": f"{city}, {state_abbr}",
                    "description": f"Mention of {city}",
                    "location": f"{city}, {state_abbr}",
                    "type": "city",
                    "components": {
                        "place": None,
                        "street_road": None,
                        "span": None,
                        "address": "",
                        "neighborhood": "",
                        "city": city,
                        "county": "",
                        "state": {"name": state_name, "abbr": state_abbr},
                        "country": {"name": "United States", "abbr": "US"},
                    },
                }
            ]
        }
    )


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
    with patch(
        "agate_nodes.place_extract.node_port.call_llm",
        return_value=_mock_place_extract_json("Chicago", "Illinois", "IL"),
    ):
        out = execute_graph(spec)
    loc = out["b"]["locations"][0]["location"]
    full = loc["full"] if isinstance(loc, dict) else loc
    assert "Chicago" in full


def test_unknown_node_type():
    spec = GraphSpec(
        name="x",
        nodes=[NodeConfig(id="z", type="NoSuchNode", params={})],
        edges=[],
    )
    with pytest.raises(GraphExecutionError, match="Unknown"):
        execute_graph(spec)


async def _fake_run_geocoding_agent(*_a, **_k):
    return {
        "places": {
            "areas": {
                "states": [],
                "counties": [],
                "cities": [{"id": "mock-city", "name": "Austin"}],
                "neighborhoods": [],
                "regions": [],
                "other": [],
            },
            "points": [],
            "needs_review": [],
        }
    }


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

    with (
        patch(
            "agate_nodes.place_extract.node_port.call_llm",
            return_value=_mock_place_extract_json("Austin", "Texas", "TX"),
        ),
        patch(
            "agate_nodes.geocode_agent.node.run_geocoding_agent",
            side_effect=_fake_run_geocoding_agent,
        ),
    ):
        out = execute_graph(spec)

    consolidated = out["n4"]["consolidated"]
    assert isinstance(consolidated, dict)
    assert "places" in consolidated
    cities = consolidated["places"]["areas"]["cities"]
    assert cities and cities[0]["name"] == "Austin"
