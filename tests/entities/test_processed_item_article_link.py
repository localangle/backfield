"""Tests for processed-item → substrate article link helpers."""

from __future__ import annotations

from backfield_entities.processed_item_article_link import (
    resolve_substrate_article_id_for_processed_item,
    substrate_article_id_from_graph_outputs,
)


def test_substrate_article_id_from_stylebook_output() -> None:
    assert (
        substrate_article_id_from_graph_outputs(
            {"stylebook_output": {"article_id": 512, "success": True}}
        )
        == 512
    )


def test_resolve_substrate_article_id_prefers_live_outputs() -> None:
    assert (
        resolve_substrate_article_id_for_processed_item(
            result_json='{"stylebook_output":{"article_id":1}}',
            outputs={"stylebook_output": {"article_id": 99}},
        )
        == 99
    )


def test_resolve_substrate_article_id_from_input_json() -> None:
    assert (
        resolve_substrate_article_id_for_processed_item(
            result_json=None,
            input_json='{"substrate_article_id": 42}',
        )
        == 42
    )
