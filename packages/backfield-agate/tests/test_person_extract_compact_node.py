"""End-to-end PersonExtract node tests for compact output mode."""

from __future__ import annotations

import json
from unittest.mock import patch

from agate_runtime import Edge, GraphSpec, NodeConfig, execute_graph


def _compact_llm_response() -> str:
    return json.dumps(
        {
            "people": [
                [
                    "John Smith",
                    "Mayor",
                    "City of Chicago",
                    1,
                    "eo",
                    "Announced a new park initiative",
                    "of",
                    [["Mayor John Smith announced a new park initiative Monday.", 0]],
                ]
            ]
        }
    )


def _full_llm_response() -> str:
    return json.dumps(
        {
            "people": [
                {
                    "name": "John Smith",
                    "title": "Mayor",
                    "affiliation": "City of Chicago",
                    "public_figure": True,
                    "type": "elected_official",
                    "role_in_story": "Announced a new park initiative",
                    "nature": "official",
                    "mentions": [
                        {
                            "text": "Mayor John Smith announced a new park initiative Monday.",
                            "quote": False,
                        }
                    ],
                }
            ]
        }
    )


def test_person_extract_compact_output_mode() -> None:
    spec = GraphSpec(
        name="compact-person",
        nodes=[
            NodeConfig(
                id="a",
                type="TextInput",
                params={"text": "Mayor John Smith announced a new park initiative Monday."},
            ),
            NodeConfig(
                id="b",
                type="PersonExtract",
                params={"output_mode": "compact"},
            ),
        ],
        edges=[
            Edge(source="a", target="b", sourceHandle="text", targetHandle="text"),
        ],
    )
    with patch(
        "agate_nodes.person_extract.node_port.call_llm",
        return_value=_compact_llm_response(),
    ):
        out = execute_graph(spec)

    people = out["person_extract"]["people"]
    assert len(people) == 1
    person = people[0]
    assert person["name"] == "John Smith"
    assert person["type"] == "elected_official"
    assert person["sort_key"] == "smith"
    assert person["mentions"]


def test_person_extract_compact_matches_full_mode_output() -> None:
    text = "Mayor John Smith announced a new park initiative Monday."
    spec_base = [
        NodeConfig(id="a", type="TextInput", params={"text": text}),
    ]
    edge = Edge(source="a", target="b", sourceHandle="text", targetHandle="text")

    compact_spec = GraphSpec(
        name="compact-person-parity",
        nodes=[
            *spec_base,
            NodeConfig(id="b", type="PersonExtract", params={"output_mode": "compact"}),
        ],
        edges=[edge],
    )
    full_spec = GraphSpec(
        name="full-person-parity",
        nodes=[
            *spec_base,
            NodeConfig(id="b", type="PersonExtract", params={"output_mode": "full"}),
        ],
        edges=[edge],
    )

    with patch(
        "agate_nodes.person_extract.node_port.call_llm",
        return_value=_compact_llm_response(),
    ):
        compact_out = execute_graph(compact_spec)
    with patch(
        "agate_nodes.person_extract.node_port.call_llm",
        return_value=_full_llm_response(),
    ):
        full_out = execute_graph(full_spec)

    assert compact_out["person_extract"]["people"] == full_out["person_extract"]["people"]


def test_person_extract_default_output_mode_is_compact() -> None:
    from agate_nodes.person_extract.node_port import PersonExtractParams

    assert PersonExtractParams().output_mode == "compact"


def test_person_extract_invalid_output_mode_defaults_to_compact() -> None:
    from agate_nodes.person_extract.node_port import PersonExtractParams

    params = PersonExtractParams(output_mode="compact_array")
    assert params.output_mode == "compact"
