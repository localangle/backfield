"""End-to-end PlaceExtract node test for compact output mode."""

import json
from unittest.mock import patch

from agate_runtime import Edge, GraphSpec, NodeConfig, execute_graph


def _compact_llm_response() -> str:
    return json.dumps(
        {
            "locations": [
                [
                    "Chicago, IL",
                    "ci",
                    "c",
                    "",
                    "Anchor city for the story.",
                    "",
                ]
            ]
        }
    )


def test_place_extract_compact_output_mode() -> None:
    spec = GraphSpec(
        name="compact-place",
        nodes=[
            NodeConfig(
                id="a",
                type="TextInput",
                params={"text": "CHICAGO — Officials met in Chicago, IL on Tuesday."},
            ),
            NodeConfig(
                id="b",
                type="PlaceExtract",
                params={"output_mode": "compact"},
            ),
        ],
        edges=[
            Edge(source="a", target="b", sourceHandle="text", targetHandle="text"),
        ],
    )
    with patch(
        "agate_nodes.place_extract.node_port.call_llm",
        return_value=_compact_llm_response(),
    ):
        out = execute_graph(spec)

    locations = out["place_extract"]["locations"]
    assert len(locations) == 1
    loc = locations[0]
    assert loc["location"]["full"] == "Chicago, IL"
    assert loc["location"]["type"] == "city"
    assert loc["nature"] == "context"
    assert loc["mentions"]
    assert set(loc["mentions"][0].keys()) == {"text"}


def test_place_extract_default_output_mode_is_compact() -> None:
    from agate_nodes.place_extract.node_port import PlaceExtractParams

    assert PlaceExtractParams().output_mode == "compact"


def test_place_extract_invalid_output_mode_defaults_to_compact() -> None:
    from agate_nodes.place_extract.node_port import PlaceExtractParams

    params = PlaceExtractParams(output_mode="not-a-mode")
    assert params.output_mode == "compact"
