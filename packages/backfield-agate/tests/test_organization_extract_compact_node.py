"""End-to-end OrganizationExtract node tests for compact output mode."""

from __future__ import annotations

import json
from unittest.mock import patch

from agate_runtime import Edge, GraphSpec, NodeConfig, execute_graph


def _compact_llm_response() -> str:
    return json.dumps(
        {
            "organizations": [
                [
                    "Chicago City Hall",
                    "gov",
                    "Announced a new park initiative",
                    "ac",
                    [["Chicago City Hall announced a new park initiative Monday.", 0]],
                ]
            ]
        }
    )


def _full_llm_response() -> str:
    return json.dumps(
        {
            "organizations": [
                {
                    "name": "Chicago City Hall",
                    "type": "government",
                    "role_in_story": "Announced a new park initiative",
                    "nature": "actor",
                    "mentions": [
                        {
                            "text": "Chicago City Hall announced a new park initiative Monday.",
                            "quote": False,
                        }
                    ],
                }
            ]
        }
    )


def test_organization_extract_compact_output_mode() -> None:
    spec = GraphSpec(
        name="compact-organization",
        nodes=[
            NodeConfig(
                id="a",
                type="TextInput",
                params={"text": "Chicago City Hall announced a new park initiative Monday."},
            ),
            NodeConfig(
                id="b",
                type="OrganizationExtract",
                params={"output_mode": "compact"},
            ),
        ],
        edges=[
            Edge(source="a", target="b", sourceHandle="text", targetHandle="text"),
        ],
    )
    with patch(
        "agate_nodes.organization_extract.node_port.call_llm",
        return_value=_compact_llm_response(),
    ):
        out = execute_graph(spec)

    organizations = out["organization_extract"]["organizations"]
    assert len(organizations) == 1
    org = organizations[0]
    assert org["name"] == "Chicago City Hall"
    assert org["type"] == "government"
    assert org["mentions"]


def test_organization_extract_compact_matches_full_mode_output() -> None:
    text = "Chicago City Hall announced a new park initiative Monday."
    spec_base = [
        NodeConfig(id="a", type="TextInput", params={"text": text}),
    ]
    edge = Edge(source="a", target="b", sourceHandle="text", targetHandle="text")

    compact_spec = GraphSpec(
        name="compact-organization-parity",
        nodes=[
            *spec_base,
            NodeConfig(id="b", type="OrganizationExtract", params={"output_mode": "compact"}),
        ],
        edges=[edge],
    )
    full_spec = GraphSpec(
        name="full-organization-parity",
        nodes=[
            *spec_base,
            NodeConfig(id="b", type="OrganizationExtract", params={"output_mode": "full"}),
        ],
        edges=[edge],
    )

    with patch(
        "agate_nodes.organization_extract.node_port.call_llm",
        return_value=_compact_llm_response(),
    ):
        compact_out = execute_graph(compact_spec)
    with patch(
        "agate_nodes.organization_extract.node_port.call_llm",
        return_value=_full_llm_response(),
    ):
        full_out = execute_graph(full_spec)

    assert (
        compact_out["organization_extract"]["organizations"]
        == full_out["organization_extract"]["organizations"]
    )


def test_organization_extract_default_output_mode_is_compact() -> None:
    from agate_nodes.organization_extract.node_port import OrganizationExtractParams

    assert OrganizationExtractParams().output_mode == "compact"


def test_organization_extract_invalid_output_mode_defaults_to_compact() -> None:
    from agate_nodes.organization_extract.node_port import OrganizationExtractParams

    params = OrganizationExtractParams(output_mode="not-a-mode")
    assert params.output_mode == "compact"
