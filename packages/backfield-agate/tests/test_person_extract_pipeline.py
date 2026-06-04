"""PersonExtract graph execution and substrate handoff."""

from __future__ import annotations

import json

from agate_runtime import PEOPLE_SMOKE_DEMO_TEXT, Edge, GraphSpec, NodeConfig, execute_graph
from agate_runtime.starter_flow import starter_people_flow_graph_spec


def _mock_people_demo_json() -> str:
    return json.dumps(
        {
            "people": [
                {
                    "name": "John Smith",
                    "title": "Mayor",
                    "affiliation": "Chicago",
                    "public_figure": True,
                    "type": "politician",
                    "role_in_story": "Announced park initiative",
                    "nature": "official",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": (
                                "Mayor John Smith of Chicago announced "
                                "a new park initiative Monday."
                            ),
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Jane Doe",
                    "title": "",
                    "affiliation": "",
                    "public_figure": False,
                    "type": "community member",
                    "role_in_story": "Resident supporting the plan",
                    "nature": "affected",
                    "nature_secondary_tags": ["source"],
                    "mentions": [
                        {
                            "text": "Jane Doe, a local resident, said she supports the plan.",
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Robert Lee",
                    "title": "",
                    "affiliation": "",
                    "public_figure": False,
                    "type": "other",
                    "role_in_story": "Arrested in vandalism case",
                    "nature": "suspect",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": (
                                "Police arrested Robert Lee in connection "
                                "with vandalism at the site"
                            ),
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Maria Garcia",
                    "title": "",
                    "affiliation": "",
                    "public_figure": False,
                    "type": "other",
                    "role_in_story": "Witnessed vandalism",
                    "nature": "witness",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {"text": "Maria Garcia witnessed the incident.", "quote": False}
                    ],
                },
                {
                    "name": "Sam Rivera",
                    "title": "Shortstop",
                    "affiliation": "Chicago Cubs",
                    "public_figure": True,
                    "type": "athlete",
                    "role_in_story": "Guest at ribbon-cutting",
                    "nature": "participant",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": (
                                "Cubs shortstop Sam Rivera attended "
                                "the ribbon-cutting as a guest."
                            ),
                            "quote": False,
                        }
                    ],
                },
            ]
        }
    )


def test_starter_people_flow_graph_spec() -> None:
    spec = starter_people_flow_graph_spec()
    assert spec.name == "starter_people_flow"
    types = {n.type for n in spec.nodes}
    assert types == {"TextInput", "PersonExtract", "DBOutput"}
    assert PEOPLE_SMOKE_DEMO_TEXT in str(spec.nodes[0].params)


def test_text_to_person_extract_to_dboutput(monkeypatch) -> None:
    from unittest.mock import patch

    spec = GraphSpec(
        name="people-pipeline",
        nodes=[
            NodeConfig(id="a", type="TextInput", params={"text": PEOPLE_SMOKE_DEMO_TEXT}),
            NodeConfig(id="b", type="PersonExtract", params={}),
            NodeConfig(
                id="c",
                type="DBOutput",
                params={"auto_apply_canonicalization": False},
            ),
        ],
        edges=[
            Edge(source="a", target="b", sourceHandle="text", targetHandle="text"),
            Edge(source="b", target="c", sourceHandle="people", targetHandle="data"),
        ],
    )
    with patch(
        "agate_nodes.person_extract.node_port.call_llm",
        return_value=_mock_people_demo_json(),
    ):
        out = execute_graph(spec)
    assert out["stylebook_output"]["success"] is True
    people = out["stylebook_output"]["people"]
    assert isinstance(people, list)
    assert len(people) >= 4
    names = {p["name"] for p in people}
    assert {"John Smith", "Jane Doe", "Robert Lee", "Maria Garcia"}.issubset(names)


def test_person_extract_empty_people_array(monkeypatch) -> None:
    from unittest.mock import patch

    spec = GraphSpec(
        name="people-empty",
        nodes=[
            NodeConfig(id="a", type="TextInput", params={"text": "No names here."}),
            NodeConfig(id="b", type="PersonExtract", params={}),
        ],
        edges=[Edge(source="a", target="b", sourceHandle="text", targetHandle="text")],
    )
    with patch(
        "agate_nodes.person_extract.node_port.call_llm",
        return_value=json.dumps({"people": []}),
    ):
        out = execute_graph(spec)
    assert out["person_extract"]["people"] == []
