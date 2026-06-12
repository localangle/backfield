"""Canonical starter graphs for local bootstrap and smoke."""

from __future__ import annotations

from agate_runtime.types import Edge, GraphSpec, NodeConfig

# Stored graph name in agate_graph.name (UI + smoke lookup).
STARTER_FLOW_GRAPH_DISPLAY_NAME = "Starter flow"
PEOPLE_STARTER_FLOW_GRAPH_DISPLAY_NAME = "People starter"

PEOPLE_SMOKE_DEMO_TEXT = (
    "Mayor John Smith of Chicago announced a new park initiative Monday. "
    "Jane Doe, a local resident, said she supports the plan. "
    "Police arrested Robert Lee in connection with vandalism at the site; "
    "Maria Garcia witnessed the incident. "
    "Cubs shortstop Sam Rivera attended the ribbon-cutting as a guest."
)

ORGANIZATIONS_STARTER_FLOW_GRAPH_DISPLAY_NAME = "Organizations starter"

ORGANIZATIONS_SMOKE_DEMO_TEXT = (
    "Chicago City Hall announced a new park initiative Monday. "
    "The Chicago Police Department said it will increase patrols near the site. "
    "Cook County approved funding for the project. "
    "The Chicago Cubs hosted a ribbon-cutting at Wrigley Field."
)

ARTICLE_METADATA_STARTER_FLOW_GRAPH_DISPLAY_NAME = "Article Metadata starter"

ARTICLE_METADATA_SMOKE_DEMO_TEXT = (
    "The city council voted Tuesday to fund a new neighborhood park on the "
    "Northwest Side. Residents packed the chamber to support the plan, and "
    "local business owners said the project could bring more foot traffic "
    "to the corridor."
)

CUSTOM_EXTRACT_STARTER_FLOW_GRAPH_DISPLAY_NAME = "Custom Extract starter"

CUSTOM_EXTRACT_SMOKE_DEMO_HEADLINE = "Riverside Bakery shares its classic banana bread recipe"

CUSTOM_EXTRACT_SMOKE_DEMO_TEXT = (
    "The Riverside Bakery shared its classic banana bread recipe this week. "
    "The recipe calls for two cups of flour, one teaspoon of baking soda, and "
    "a pinch of salt. Bakers should mash three ripe bananas, then fold in "
    "half a cup of melted butter before pouring the batter into a greased pan."
)


def starter_geocode_flow_graph_spec() -> GraphSpec:
    """Golden-path starter: geocode then persist, with DBOutput wired directly from GeocodeAgent.

    Positions match the graph exported from Agate UI for this layout.
    """
    return GraphSpec(
        name="starter_flow",
        nodes=[
            NodeConfig(
                id="n1",
                type="TextInput",
                params={"text": "We visited Chicago, IL and Austin, TX."},
                position={"x": 0.0, "y": 0.0},
            ),
            NodeConfig(
                id="n2",
                type="PlaceExtract",
                params={},
                position={"x": 337.487868852459, "y": 46.08393442622952},
            ),
            NodeConfig(
                id="n3",
                type="GeocodeAgent",
                params={},
                position={"x": 596.3311475409837, "y": 16.26491803278691},
            ),
            NodeConfig(
                id="n5",
                type="DBOutput",
                params={
                    "stylebook_matching_enabled": True,
                    "stylebook_id": None,
                    "canonicalization_mode": "ai_assisted",
                    "auto_apply_canonicalization": True,
                    "adjudication_model": "gpt-5-nano",
                },
                position={"x": 865.9777049180329, "y": 46.08393442622952},
            ),
        ],
        edges=[
            Edge(source="n1", target="n2", sourceHandle="text", targetHandle="text"),
            Edge(
                source="n2",
                target="n3",
                sourceHandle="locations",
                targetHandle="locations",
            ),
            Edge(
                source="n3",
                target="n5",
                sourceHandle="locations",
                targetHandle="data",
            ),
        ],
    )


def starter_people_flow_graph_spec() -> GraphSpec:
    """Golden-path people ingest: TextInput → PersonExtract → DBOutput."""
    return GraphSpec(
        name="starter_people_flow",
        nodes=[
            NodeConfig(
                id="n1",
                type="TextInput",
                params={"text": PEOPLE_SMOKE_DEMO_TEXT},
                position={"x": 0.0, "y": 0.0},
            ),
            NodeConfig(
                id="n2",
                type="PersonExtract",
                params={},
                position={"x": 337.0, "y": 46.0},
            ),
            NodeConfig(
                id="n3",
                type="DBOutput",
                params={
                    "stylebook_matching_enabled": True,
                    "auto_apply_canonicalization": False,
                    "reconciliation_policy": "smart_merge",
                },
                position={"x": 620.0, "y": 46.0},
            ),
        ],
        edges=[
            Edge(source="n1", target="n2", sourceHandle="text", targetHandle="text"),
            Edge(source="n2", target="n3", sourceHandle="people", targetHandle="data"),
        ],
    )


def starter_organizations_flow_graph_spec() -> GraphSpec:
    """Golden-path organizations ingest: TextInput → OrganizationExtract → DBOutput."""
    return GraphSpec(
        name="starter_organizations_flow",
        nodes=[
            NodeConfig(
                id="n1",
                type="TextInput",
                params={"text": ORGANIZATIONS_SMOKE_DEMO_TEXT},
                position={"x": 0.0, "y": 0.0},
            ),
            NodeConfig(
                id="n2",
                type="OrganizationExtract",
                params={},
                position={"x": 337.0, "y": 46.0},
            ),
            NodeConfig(
                id="n3",
                type="DBOutput",
                params={
                    "stylebook_matching_enabled": True,
                    "auto_apply_canonicalization": False,
                    "reconciliation_policy": "smart_merge",
                },
                position={"x": 620.0, "y": 46.0},
            ),
        ],
        edges=[
            Edge(source="n1", target="n2", sourceHandle="text", targetHandle="text"),
            Edge(
                source="n2",
                target="n3",
                sourceHandle="organizations",
                targetHandle="data",
            ),
        ],
    )


def starter_custom_extract_flow_graph_spec() -> GraphSpec:
    """Golden-path custom records ingest: JSONInput (recipe) → CustomExtract → DBOutput."""
    return GraphSpec(
        name="starter_custom_extract_flow",
        nodes=[
            NodeConfig(
                id="n1",
                type="JSONInput",
                params={
                    "headline": CUSTOM_EXTRACT_SMOKE_DEMO_HEADLINE,
                    "text": CUSTOM_EXTRACT_SMOKE_DEMO_TEXT,
                },
                position={"x": 0.0, "y": 0.0},
            ),
            NodeConfig(
                id="n2",
                type="CustomExtract",
                params={
                    "record_type": "ingredients",
                    "label": "Ingredients",
                    "fields": [
                        {
                            "name": "name",
                            "label": "Name",
                            "type": "string",
                            "description": "The ingredient as named in the story.",
                        },
                        {
                            "name": "quantity",
                            "label": "Quantity",
                            "type": "string",
                            "description": "The amount called for, as written.",
                        },
                    ],
                    "instructions": "Extract every ingredient the recipe calls for.",
                },
                position={"x": 337.0, "y": 46.0},
            ),
            NodeConfig(
                id="n3",
                type="DBOutput",
                params={
                    "stylebook_matching_enabled": False,
                    "semantic_indexing_enabled": False,
                    "reconciliation_policy": "smart_merge",
                },
                position={"x": 620.0, "y": 46.0},
            ),
        ],
        edges=[
            Edge(source="n1", target="n2", sourceHandle="text", targetHandle="text"),
            Edge(
                source="n2",
                target="n3",
                sourceHandle="custom_records",
                targetHandle="data",
            ),
        ],
    )


def starter_article_metadata_flow_graph_spec() -> GraphSpec:
    """Golden-path article metadata ingest: TextInput → ArticleMetadata → DBOutput."""
    return GraphSpec(
        name="starter_article_metadata_flow",
        nodes=[
            NodeConfig(
                id="n1",
                type="TextInput",
                params={"text": ARTICLE_METADATA_SMOKE_DEMO_TEXT},
                position={"x": 0.0, "y": 0.0},
            ),
            NodeConfig(
                id="n2",
                type="ArticleMetadata",
                params={"prompt_preset": "subject"},
                position={"x": 337.0, "y": 46.0},
            ),
            NodeConfig(
                id="n3",
                type="DBOutput",
                params={
                    "stylebook_matching_enabled": False,
                    "semantic_indexing_enabled": False,
                    "reconciliation_policy": "smart_merge",
                },
                position={"x": 620.0, "y": 46.0},
            ),
        ],
        edges=[
            Edge(source="n1", target="n2", sourceHandle="text", targetHandle="text"),
            Edge(source="n2", target="n3", sourceHandle="text", targetHandle="data"),
        ],
    )
