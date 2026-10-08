"""Entity extract nodes ask the original GPT-5 family for ``reasoning_effort="low"``.

At the ``"minimal"`` default, gpt-5-nano answers the extract prompts with the empty
envelope (``{"locations": []}``, 14 completion tokens) for articles full of entities,
and the run still reports success (issue #176).
"""

import json
from typing import Any
from unittest.mock import patch

import pytest
from agate_nodes.extraction.shared_llm import extract_reasoning_effort
from agate_runtime import Edge, GraphSpec, NodeConfig, execute_graph


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-5", "low"),
        ("gpt-5-mini", "low"),
        ("gpt-5-nano", "low"),
        ("openai/gpt-5-nano", "low"),
        ("OpenAI/GPT-5-Nano", "low"),
        ("gpt-5-nano-2025-08-07", "low"),
        ("gpt-5.6-terra", None),
        ("openai/gpt-5.6-luna", None),
        ("gpt-5.1", None),
        ("gpt-5-chat-latest", None),
        ("gpt-4o-mini", None),
        ("anthropic/claude-sonnet-4-5-20250929", None),
        ("gemini/gemini-2.5-flash", None),
    ],
)
def test_extract_reasoning_effort(model: str, expected: str | None) -> None:
    assert extract_reasoning_effort(model) == expected


_NODES = [
    ("PlaceExtract", "place_extract", {"locations": []}),
    ("PersonExtract", "person_extract", {"people": []}),
    ("OrganizationExtract", "organization_extract", {"organizations": []}),
]


def _single_node_spec(node_type: str, model: str) -> GraphSpec:
    return GraphSpec(
        name="extract-effort",
        nodes=[
            NodeConfig(
                id="a",
                type="TextInput",
                params={"text": "BALTIMORE — Mayor Jane Doe spoke at Acme Corp in Towson."},
            ),
            NodeConfig(id="b", type=node_type, params={"model": model}),
        ],
        edges=[Edge(source="a", target="b", sourceHandle="text", targetHandle="text")],
    )


@pytest.mark.parametrize(("node_type", "module", "empty_response"), _NODES)
@pytest.mark.parametrize(
    ("model", "expected"),
    [("gpt-5-nano", "low"), ("gpt-4o-mini", None), ("gpt-5.6-terra", None)],
)
def test_extract_node_passes_reasoning_effort(
    node_type: str,
    module: str,
    empty_response: dict[str, Any],
    model: str,
    expected: str | None,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_call_llm(**kwargs: Any) -> str:
        calls.append(kwargs)
        return json.dumps(empty_response)

    with patch(f"agate_nodes.{module}.node_port.call_llm", side_effect=fake_call_llm):
        execute_graph(_single_node_spec(node_type, model))

    assert len(calls) == 1
    assert calls[0]["model"] == model
    assert calls[0]["reasoning_effort"] == expected


def test_chunked_extract_passes_reasoning_effort() -> None:
    long_text = "\n\n".join(
        f"Section {i} mentions Chicago, IL in the narrative. " + ("word " * 120)
        for i in range(6)
    )
    spec = GraphSpec(
        name="chunked-effort",
        nodes=[
            NodeConfig(id="a", type="TextInput", params={"text": long_text}),
            NodeConfig(
                id="c",
                type="DocumentChunker",
                params={"target_tokens": 120, "overlap_tokens": 20},
            ),
            NodeConfig(id="b", type="PlaceExtract", params={"model": "gpt-5-nano"}),
        ],
        edges=[
            Edge(source="a", target="c", sourceHandle="text", targetHandle="text"),
            Edge(source="c", target="b", sourceHandle="text", targetHandle="text"),
        ],
    )
    calls: list[dict[str, Any]] = []

    def fake_call_llm(**kwargs: Any) -> str:
        calls.append(kwargs)
        return json.dumps({"locations": []})

    with patch(
        "agate_nodes.extraction.chunked_entity_extract.call_llm",
        side_effect=fake_call_llm,
    ):
        out = execute_graph(spec)

    assert out["document_chunker"]["chunking_summary"]["chunk_count"] >= 2
    assert len(calls) >= 2
    assert {c["reasoning_effort"] for c in calls} == {"low"}
