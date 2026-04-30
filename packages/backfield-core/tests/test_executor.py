"""Unit tests for graph execution."""

import json
import os
from unittest.mock import MagicMock, patch

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
    assert "__outputKeysByNodeId" not in out
    loc = out["place_extract"]["locations"][0]["location"]
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


def test_json_input_requires_dict_and_text():
    from backfield_core.nodes.json_input import run_json_input

    with pytest.raises(ValueError, match="JSON object"):
        run_json_input("not-a-dict", {})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="text"):
        run_json_input({}, {})
    with pytest.raises(ValueError, match="text"):
        run_json_input({"text": "  \n"}, {})


def test_json_input_pass_through_strips_on_change():
    from backfield_core.nodes.json_input import run_json_input

    out = run_json_input(
        {
            "text": "Article body.",
            "headline": "Title",
            "results": {"images": ["x.png"]},
            "onChange": None,
        },
        {},
    )
    assert out["text"] == "Article body."
    assert out["headline"] == "Title"
    assert out["results"] == {"images": ["x.png"]}
    assert "onChange" not in out


def test_json_input_to_place_extract():
    spec = GraphSpec(
        name="j",
        nodes=[
            NodeConfig(
                id="j1",
                type="JSONInput",
                params={
                    "text": "News from Chicago, IL today.",
                    "headline": "Morning edition",
                },
            ),
            NodeConfig(id="b", type="PlaceExtract", params={}),
        ],
        edges=[
            Edge(source="j1", target="b", sourceHandle="text", targetHandle="text"),
        ],
    )
    with patch(
        "agate_nodes.place_extract.node_port.call_llm",
        return_value=_mock_place_extract_json("Chicago", "Illinois", "IL"),
    ):
        out = execute_graph(spec)
    assert "json_input" in out
    assert out["json_input"]["headline"] == "Morning edition"
    loc = out["place_extract"]["locations"][0]["location"]
    full = loc["full"] if isinstance(loc, dict) else loc
    assert "Chicago" in full


def test_s3_input_requires_bucket():
    from backfield_core.nodes.s3_input import run_s3_input

    with pytest.raises(ValueError, match="bucket"):
        run_s3_input({"bucket": "", "folder_path": ""}, {})


def test_s3_input_first_valid_json_file():
    """First JSON key with non-empty text wins; earlier invalid keys are skipped."""
    from backfield_core.nodes.s3_input import run_s3_input

    class _Body:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    client = MagicMock()
    client.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "prefix/broken.json"},
            {"Key": "prefix/bad.json"},
            {"Key": "prefix/good.json"},
        ],
        "IsTruncated": False,
    }

    def _get_object(*_a, **kwargs):
        key = str(kwargs.get("Key") or "")
        if key.endswith("broken.json"):
            return {"Body": _Body(b"not json")}
        if key.endswith("bad.json"):
            return {"Body": _Body(json.dumps({"text": ""}).encode())}
        if key.endswith("good.json"):
            return {
                "Body": _Body(
                    json.dumps(
                        {
                            "text": "Story from S3.",
                            "headline": "H",
                            "url": "https://example.com/a",
                        }
                    ).encode()
                )
            }
        raise AssertionError(key)

    client.get_object.side_effect = _get_object

    with patch.dict(
        os.environ,
        {"AWS_ACCESS_KEY_ID": "ak", "AWS_SECRET_ACCESS_KEY": "sk"},
        clear=False,
    ):
        with patch("backfield_core.nodes.s3_input.boto3.client", return_value=client):
            out = run_s3_input({"bucket": "my-bucket", "folder_path": "prefix"}, {})

    assert out["text"] == "Story from S3."
    assert out["headline"] == "H"
    assert out["url"] == "https://example.com/a"
    assert out["total_files"] == 3
    assert out["processed_files"] == 1
    assert out["skipped_files"] == 2  # invalid JSON + empty text
    assert out["source_file"] == "prefix/good.json"


def test_s3_input_to_place_extract():
    spec = GraphSpec(
        name="s3",
        nodes=[
            NodeConfig(id="s3n", type="S3Input", params={"bucket": "b", "folder_path": "p"}),
            NodeConfig(id="pe", type="PlaceExtract", params={}),
        ],
        edges=[
            Edge(source="s3n", target="pe", sourceHandle="text", targetHandle="text"),
        ],
    )
    client = MagicMock()
    client.list_objects_v2.return_value = {
        "Contents": [{"Key": "p/a.json"}],
        "IsTruncated": False,
    }
    class _Body2:
        def read(self) -> bytes:
            return json.dumps({"text": "News from Chicago, IL today."}).encode()

    client.get_object.return_value = {"Body": _Body2()}

    with patch.dict(
        os.environ,
        {"AWS_ACCESS_KEY_ID": "ak", "AWS_SECRET_ACCESS_KEY": "sk"},
        clear=False,
    ):
        with patch("backfield_core.nodes.s3_input.boto3.client", return_value=client):
            with patch(
                "agate_nodes.place_extract.node_port.call_llm",
                return_value=_mock_place_extract_json("Chicago", "Illinois", "IL"),
            ):
                out = execute_graph(spec)

    assert "s3_input" in out
    assert out["s3_input"]["text"].startswith("News from")
    loc = out["place_extract"]["locations"][0]["location"]
    full = loc["full"] if isinstance(loc, dict) else loc
    assert "Chicago" in full


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
            NodeConfig(id="n5", type="DBOutput", params={}),
        ],
        edges=[
            Edge(source="n1", target="n2", sourceHandle="text", targetHandle="text"),
            Edge(source="n2", target="n3", sourceHandle="locations", targetHandle="locations"),
            Edge(source="n3", target="n4", sourceHandle="locations", targetHandle="data"),
            Edge(source="n4", target="n5", sourceHandle="consolidated", targetHandle="data"),
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

    assert "__outputKeysByNodeId" not in out
    consolidated = out["json_output"]["consolidated"]
    assert isinstance(consolidated, dict)
    assert "places" in consolidated
    cities = consolidated["places"]["areas"]["cities"]
    assert cities and cities[0]["name"] == "Austin"

    db_out = out["stylebook_output"]
    assert db_out.get("success") is True
    assert "places" in db_out


def test_dboutput_direct_upstream_without_json_output():
    """DBOutput must not require an Output node — upstream-only merge (agate parity)."""
    spec = GraphSpec(
        name="pipeline",
        nodes=[
            NodeConfig(id="n1", type="TextInput", params={"text": "Meetings in Austin, TX."}),
            NodeConfig(id="n2", type="PlaceExtract", params={}),
            NodeConfig(id="n3", type="GeocodeAgent", params={}),
            NodeConfig(id="n5", type="DBOutput", params={}),
        ],
        edges=[
            Edge(source="n1", target="n2", sourceHandle="text", targetHandle="text"),
            Edge(source="n2", target="n3", sourceHandle="locations", targetHandle="locations"),
            Edge(source="n3", target="n5", sourceHandle="locations", targetHandle="data"),
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

    assert "__outputKeysByNodeId" not in out
    db_out = out["stylebook_output"]
    assert db_out.get("success") is True
    assert "places" in db_out
    cities = db_out["places"]["areas"]["cities"]
    assert cities and cities[0]["name"] == "Austin"


def test_advanced_geocode_agent_dboutput_direct_upstream():
    """AdvancedGeocodeAgent uses the same places merge path as GeocodeAgent for DBOutput."""
    spec = GraphSpec(
        name="pipeline-advanced-geocode",
        nodes=[
            NodeConfig(id="n1", type="TextInput", params={"text": "Meetings in Austin, TX."}),
            NodeConfig(id="n2", type="PlaceExtract", params={}),
            NodeConfig(
                id="n3",
                type="AdvancedGeocodeAgent",
                params={"evaluationModel": "gpt-5-mini", "routerModel": "gpt-5-nano"},
            ),
            NodeConfig(id="n5", type="DBOutput", params={}),
        ],
        edges=[
            Edge(source="n1", target="n2", sourceHandle="text", targetHandle="text"),
            Edge(source="n2", target="n3", sourceHandle="locations", targetHandle="locations"),
            Edge(source="n3", target="n5", sourceHandle="locations", targetHandle="data"),
        ],
    )

    with (
        patch(
            "agate_nodes.place_extract.node_port.call_llm",
            return_value=_mock_place_extract_json("Austin", "Texas", "TX"),
        ),
        patch(
            "agate_nodes.geocode_agent.node.run_advanced_geocoding_agent",
            side_effect=_fake_run_geocoding_agent,
        ),
    ):
        out = execute_graph(spec)

    assert "advanced_geocode_agent" in out
    assert "__outputKeysByNodeId" not in out
    db_out = out["stylebook_output"]
    assert db_out.get("success") is True
    assert "places" in db_out
    cities = db_out["places"]["areas"]["cities"]
    assert cities and cities[0]["name"] == "Austin"


def test_json_input_article_fields_reach_dboutput_after_geocode():
    """Geocode must flatten executor namespacing so headline/url survive DBOutput merge."""
    spec = GraphSpec(
        name="article-pipeline",
        nodes=[
            NodeConfig(
                id="j1",
                type="JSONInput",
                params={
                    "text": "A man was shot in West Garfield Park.",
                    "headline": "Man fatally shot in West Garfield Park",
                    "url": "https://chicago.suntimes.com/crime/2026/04/19/example",
                    "publication": "Chicago Sun-Times",
                    "author": "Sun-Times Wire",
                },
            ),
            NodeConfig(id="n2", type="PlaceExtract", params={}),
            NodeConfig(id="n3", type="GeocodeAgent", params={}),
            NodeConfig(id="n5", type="DBOutput", params={}),
        ],
        edges=[
            Edge(source="j1", target="n2", sourceHandle="text", targetHandle="text"),
            Edge(source="n2", target="n3", sourceHandle="locations", targetHandle="locations"),
            Edge(source="n3", target="n5", sourceHandle="locations", targetHandle="data"),
        ],
    )

    with (
        patch(
            "agate_nodes.place_extract.node_port.call_llm",
            return_value=_mock_place_extract_json("Chicago", "Illinois", "IL"),
        ),
        patch(
            "agate_nodes.geocode_agent.node.run_geocoding_agent",
            side_effect=_fake_run_geocoding_agent,
        ),
    ):
        out = execute_graph(spec)

    db_out = out["stylebook_output"]
    assert db_out.get("success") is True
    assert db_out.get("headline") == "Man fatally shot in West Garfield Park"
    assert db_out.get("url") == "https://chicago.suntimes.com/crime/2026/04/19/example"
    assert db_out.get("author") == "Sun-Times Wire"
    assert db_out.get("publication") == "Chicago Sun-Times"
