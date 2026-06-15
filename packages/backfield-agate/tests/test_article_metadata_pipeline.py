"""ArticleMetadata graph execution and DBOutput handoff."""

from __future__ import annotations

import json
from unittest.mock import patch

from agate_runtime import (
    ARTICLE_METADATA_SMOKE_DEMO_TEXT,
    Edge,
    GraphSpec,
    NodeConfig,
    execute_graph,
)
from agate_runtime.starter_flow import starter_article_metadata_flow_graph_spec


def _mock_article_metadata_json() -> str:
    return json.dumps(
        {
            "subject": "government_action",
            "rationale": "City council vote on a neighborhood park.",
            "confidence": 0.82,
        }
    )


def test_starter_article_metadata_flow_graph_spec() -> None:
    spec = starter_article_metadata_flow_graph_spec()
    assert spec.name == "starter_article_metadata_flow"
    types = {n.type for n in spec.nodes}
    assert types == {"TextInput", "ArticleMetadata", "DBOutput"}
    assert ARTICLE_METADATA_SMOKE_DEMO_TEXT in str(spec.nodes[0].params)


def test_text_to_article_metadata_to_dboutput() -> None:
    spec = GraphSpec(
        name="article-metadata-pipeline",
        nodes=[
            NodeConfig(
                id="a",
                type="TextInput",
                params={"text": ARTICLE_METADATA_SMOKE_DEMO_TEXT},
            ),
            NodeConfig(id="b", type="ArticleMetadata", params={"prompt_preset": "subject"}),
            NodeConfig(
                id="c",
                type="DBOutput",
                params={
                    "stylebook_matching_enabled": False,
                    "semantic_indexing_enabled": False,
                },
            ),
        ],
        edges=[
            Edge(source="a", target="b", sourceHandle="text", targetHandle="text"),
            Edge(source="b", target="c", sourceHandle="text", targetHandle="data"),
        ],
    )
    with patch(
        "agate_nodes.article_metadata.node_port.call_llm",
        return_value=_mock_article_metadata_json(),
    ):
        out = execute_graph(spec)
    so = out["stylebook_output"]
    assert so["success"] is True
    meta = so["article_metadata"]
    assert meta["meta_type"] == "subject"
    assert meta["subject"] == "government_action"
    assert meta["category"] == "government_action"
    assert meta["confidence"] == 0.82
    assert so["text"] == ARTICLE_METADATA_SMOKE_DEMO_TEXT
