"""Unit tests for graph execution."""

import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest
from agate_runtime import Edge, GraphSpec, NodeConfig, build_execution_levels, execute_graph
from agate_runtime.executor import GraphExecutionError


def _mock_place_extract_json(city: str, state_name: str, state_abbr: str) -> str:
    return json.dumps(
        {
            "locations": [
                {
                    "original_text": f"{city}, {state_abbr}",
                    "description": f"Mention of {city}",
                    "geocode_hints": "",
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
    from agate_runtime.nodes.json_input import run_json_input

    with pytest.raises(ValueError, match="JSON object"):
        run_json_input("not-a-dict", {})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="text"):
        run_json_input({}, {})
    with pytest.raises(ValueError, match="text"):
        run_json_input({"text": "  \n"}, {})


def test_json_input_pass_through_strips_on_change():
    from agate_runtime.nodes.json_input import run_json_input

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
    from agate_runtime.nodes.s3_input import run_s3_input

    with pytest.raises(ValueError, match="bucket"):
        run_s3_input({"bucket": "", "folder_path": ""}, {})


def test_s3_input_strips_s3_uri_prefix_from_bucket():
    from agate_runtime.nodes.s3_input import run_s3_input

    client = MagicMock()
    client.list_objects_v2.return_value = {"IsTruncated": False}

    with patch("agate_nodes.s3_input.node._s3_client", return_value=client):
        with pytest.raises(ValueError, match="No JSON objects"):
            run_s3_input({"bucket": "s3://my-bucket", "folder_path": ""}, {})

    client.list_objects_v2.assert_called_once()
    assert client.list_objects_v2.call_args.kwargs["Bucket"] == "my-bucket"


def test_s3_input_first_valid_json_file():
    """First JSON key with non-empty text wins; earlier invalid keys are skipped."""
    from agate_runtime.nodes.s3_input import run_s3_input

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
        with patch("agate_nodes.s3_input.node.boto3.client", return_value=client):
            out = run_s3_input({"bucket": "my-bucket", "folder_path": "prefix"}, {})

    assert out["text"] == "Story from S3."
    assert out["headline"] == "H"
    assert out["url"] == "https://example.com/a"
    assert out["total_files"] == 3
    assert out["processed_files"] == 1
    assert out["skipped_files"] == 2
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
        with patch("agate_nodes.s3_input.node.boto3.client", return_value=client):
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
            "agate_nodes.geocode_agent.node.run_advanced_geocoding_agent",
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
            "agate_nodes.geocode_agent.node.run_advanced_geocoding_agent",
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


def test_geocode_agent_model_params_dboutput_direct_upstream():
    """GeocodeAgent with evaluation/router model params uses the same DBOutput merge path."""
    spec = GraphSpec(
        name="pipeline-geocode-models",
        nodes=[
            NodeConfig(id="n1", type="TextInput", params={"text": "Meetings in Austin, TX."}),
            NodeConfig(id="n2", type="PlaceExtract", params={}),
            NodeConfig(
                id="n3",
                type="GeocodeAgent",
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

    assert "geocode_agent" in out
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
            "agate_nodes.geocode_agent.node.run_advanced_geocoding_agent",
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


def _fanout_extract_spec() -> GraphSpec:
    return GraphSpec(
        name="fanout-extracts",
        nodes=[
            NodeConfig(
                id="in",
                type="TextInput",
                params={"text": "Mayor Jane Doe works for City Hall in Chicago, IL."},
            ),
            NodeConfig(id="org", type="OrganizationExtract", params={}),
            NodeConfig(id="per", type="PersonExtract", params={}),
            NodeConfig(id="plc", type="PlaceExtract", params={}),
        ],
        edges=[
            Edge(source="in", target="org", sourceHandle="text", targetHandle="text"),
            Edge(source="in", target="per", sourceHandle="text", targetHandle="text"),
            Edge(source="in", target="plc", sourceHandle="text", targetHandle="text"),
        ],
    )


def _mock_org_json() -> str:
    return json.dumps(
        {
            "organizations": [
                {
                    "name": "City Hall",
                    "type": "government",
                    "role_in_story": "Employer",
                    "nature": "actor",
                    "nature_secondary_tags": [],
                    "mentions": [{"text": "City Hall", "quote": False}],
                }
            ]
        }
    )


def _mock_person_json() -> str:
    return json.dumps(
        {
            "people": [
                {
                    "name": "Jane Doe",
                    "title": "Mayor",
                    "affiliation": "City Hall",
                    "public_figure": True,
                    "type": "politician",
                    "role_in_story": "Subject",
                    "nature": "official",
                    "nature_secondary_tags": [],
                    "mentions": [{"text": "Mayor Jane Doe", "quote": False}],
                }
            ]
        }
    )


def test_build_execution_levels_fan_out():
    levels = build_execution_levels(_fanout_extract_spec())
    assert levels == [["in"], ["org", "per", "plc"]]


def test_build_execution_levels_linear_chain():
    spec = GraphSpec(
        name="linear",
        nodes=[
            NodeConfig(id="a", type="TextInput", params={"text": "x"}),
            NodeConfig(id="b", type="PlaceExtract", params={}),
            NodeConfig(id="c", type="GeocodeAgent", params={}),
        ],
        edges=[
            Edge(source="a", target="b", sourceHandle="text", targetHandle="text"),
            Edge(source="b", target="c", sourceHandle="locations", targetHandle="locations"),
        ],
    )
    assert build_execution_levels(spec) == [["a"], ["b"], ["c"]]


def test_build_execution_levels_diamond_merge():
    spec = GraphSpec(
        name="diamond",
        nodes=[
            NodeConfig(id="a", type="TextInput", params={"text": "x"}),
            NodeConfig(id="b", type="PlaceExtract", params={}),
            NodeConfig(id="c", type="PersonExtract", params={}),
            NodeConfig(id="d", type="Output", params={}),
        ],
        edges=[
            Edge(source="a", target="b", sourceHandle="text", targetHandle="text"),
            Edge(source="a", target="c", sourceHandle="text", targetHandle="text"),
            Edge(source="b", target="d", sourceHandle="locations", targetHandle="data"),
            Edge(source="c", target="d", sourceHandle="people", targetHandle="data"),
        ],
    )
    levels = build_execution_levels(spec)
    assert levels[0] == ["a"]
    assert set(levels[1]) == {"b", "c"}
    assert levels[2] == ["d"]


def test_build_execution_levels_cycle_raises():
    spec = GraphSpec(
        name="cycle",
        nodes=[
            NodeConfig(id="a", type="TextInput", params={"text": "x"}),
            NodeConfig(id="b", type="PlaceExtract", params={}),
        ],
        edges=[
            Edge(source="a", target="b", sourceHandle="text", targetHandle="text"),
            Edge(source="b", target="a", sourceHandle="locations", targetHandle="text"),
        ],
    )
    with pytest.raises(GraphExecutionError, match="Cycle"):
        build_execution_levels(spec)


def test_fan_out_parallel_levels_faster_than_sequential(monkeypatch: pytest.MonkeyPatch):
    sleep_s = 0.25
    spec = _fanout_extract_spec()

    def slow_org(*_a, **_k):
        time.sleep(sleep_s)
        return _mock_org_json()

    def slow_person(*_a, **_k):
        time.sleep(sleep_s)
        return _mock_person_json()

    def slow_place(*_a, **_k):
        time.sleep(sleep_s)
        return _mock_place_extract_json("Chicago", "Illinois", "IL")

    patches = (
        patch("agate_nodes.organization_extract.node_port.call_llm", side_effect=slow_org),
        patch("agate_nodes.person_extract.node_port.call_llm", side_effect=slow_person),
        patch("agate_nodes.place_extract.node_port.call_llm", side_effect=slow_place),
    )
    for p in patches:
        p.start()
    try:
        monkeypatch.delenv("BACKFIELD_PARALLEL_GRAPH_LEVELS", raising=False)
        t0 = time.perf_counter()
        out_seq = execute_graph(spec)
        seq_elapsed = time.perf_counter() - t0

        monkeypatch.setenv("BACKFIELD_PARALLEL_GRAPH_LEVELS", "1")
        t1 = time.perf_counter()
        out_par = execute_graph(spec)
        par_elapsed = time.perf_counter() - t1
    finally:
        for p in patches:
            p.stop()

    assert seq_elapsed >= sleep_s * 3 * 0.85
    assert par_elapsed < sleep_s * 2
    assert set(out_seq.keys()) == set(out_par.keys())
    assert out_seq["organization_extract"] == out_par["organization_extract"]
    assert out_seq["person_extract"] == out_par["person_extract"]
    assert out_seq["place_extract"] == out_par["place_extract"]
