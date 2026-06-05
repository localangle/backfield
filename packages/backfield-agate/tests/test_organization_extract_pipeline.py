"""OrganizationExtract graph execution and substrate handoff."""

from __future__ import annotations

import json
from unittest.mock import patch

from agate_runtime import (
    ORGANIZATIONS_SMOKE_DEMO_TEXT,
    Edge,
    GraphSpec,
    NodeConfig,
    execute_graph,
)
from agate_runtime.starter_flow import starter_organizations_flow_graph_spec


def _mock_organizations_demo_json() -> str:
    return json.dumps(
        {
            "organizations": [
                {
                    "name": "Chicago City Hall",
                    "type": "government",
                    "role_in_story": "Announced park initiative",
                    "nature": "actor",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": "Chicago City Hall announced a new park initiative Monday.",
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Chicago Police Department",
                    "type": "law_enforcement",
                    "role_in_story": "Will increase patrols",
                    "nature": "regulator",
                    "nature_secondary_tags": ["source"],
                    "mentions": [
                        {
                            "text": (
                                "The Chicago Police Department said it will increase "
                                "patrols near the site."
                            ),
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Cook County",
                    "type": "government",
                    "role_in_story": "Approved funding",
                    "nature": "source",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": "Cook County approved funding for the project.",
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Chicago Cubs",
                    "type": "sports_team",
                    "role_in_story": "Hosted ribbon-cutting",
                    "nature": "context",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": "The Chicago Cubs hosted a ribbon-cutting at Wrigley Field.",
                            "quote": False,
                        }
                    ],
                },
            ]
        }
    )


def test_starter_organizations_flow_graph_spec() -> None:
    spec = starter_organizations_flow_graph_spec()
    assert spec.name == "starter_organizations_flow"
    types = {n.type for n in spec.nodes}
    assert types == {"TextInput", "OrganizationExtract", "DBOutput"}
    assert ORGANIZATIONS_SMOKE_DEMO_TEXT in str(spec.nodes[0].params)


def test_text_to_organization_extract_to_dboutput() -> None:
    spec = GraphSpec(
        name="organizations-pipeline",
        nodes=[
            NodeConfig(
                id="a",
                type="TextInput",
                params={"text": ORGANIZATIONS_SMOKE_DEMO_TEXT},
            ),
            NodeConfig(id="b", type="OrganizationExtract", params={}),
            NodeConfig(
                id="c",
                type="DBOutput",
                params={"auto_apply_canonicalization": False},
            ),
        ],
        edges=[
            Edge(source="a", target="b", sourceHandle="text", targetHandle="text"),
            Edge(source="b", target="c", sourceHandle="organizations", targetHandle="data"),
        ],
    )
    with patch(
        "agate_nodes.organization_extract.node_port.call_llm",
        return_value=_mock_organizations_demo_json(),
    ):
        out = execute_graph(spec)
    assert out["stylebook_output"]["success"] is True
    organizations = out["stylebook_output"]["organizations"]
    assert isinstance(organizations, list)
    assert len(organizations) >= 4
    names = {o["name"] for o in organizations}
    assert {
        "Chicago City Hall",
        "Chicago Police Department",
        "Cook County",
        "Chicago Cubs",
    }.issubset(names)


def test_organization_extract_empty_array() -> None:
    spec = GraphSpec(
        name="organizations-empty",
        nodes=[
            NodeConfig(id="a", type="TextInput", params={"text": "No orgs here."}),
            NodeConfig(id="b", type="OrganizationExtract", params={}),
        ],
        edges=[Edge(source="a", target="b", sourceHandle="text", targetHandle="text")],
    )
    with patch(
        "agate_nodes.organization_extract.node_port.call_llm",
        return_value=json.dumps({"organizations": []}),
    ):
        out = execute_graph(spec)
    assert out["organization_extract"]["organizations"] == []
