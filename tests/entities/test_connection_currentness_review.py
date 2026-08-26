"""Resolved-edge currentness review tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

from backfield_entities.connections.currentness_review import (
    ResolvedEdgeCurrentnessReviewItem,
    review_resolved_edge_currentness,
)
from backfield_entities.connections.types import AutoConnectionEdgeProposal


def _item(
    review_id: str,
    *,
    quote: str = "Jane works for Acme.",
) -> ResolvedEdgeCurrentnessReviewItem:
    return ResolvedEdgeCurrentnessReviewItem(
        review_id=review_id,
        edge=AutoConnectionEdgeProposal(
            from_entity_id="person-1",
            to_entity_id="org-1",
            description="Jane works for Acme.",
            nature="works_for",
            confidence=0.95,
            quote=quote,
        ),
        from_entity_type="person",
        to_entity_type="organization",
    )


def test_reviews_every_supplied_dynamic_edge() -> None:
    call_llm = MagicMock(
        return_value=json.dumps(
            {
                "decisions": [
                    {
                        "review_id": "edge-1",
                        "asserted_currentness": "current",
                        "reason": "Present-tense employment.",
                    },
                    {
                        "review_id": "edge-2",
                        "asserted_currentness": "unspecified",
                        "reason": "The wording does not establish timing.",
                    },
                ]
            }
        )
    )

    result = review_resolved_edge_currentness(
        items=(_item("edge-1"), _item("edge-2", quote="Jane mentioned Acme.")),
        reference_at=datetime(2026, 8, 20, tzinfo=UTC),
        model="test-model",
        model_config_id="7",
        call_llm=call_llm,
    )

    assert result.counts.attempted == 2
    assert result.counts.reviewed == 2
    assert result.counts.current == 1
    assert result.counts.unspecified == 1
    assert result.counts.missing_decisions == 0
    assert result.edges_by_review_id["edge-1"].asserted_currentness == "current"
    assert result.edges_by_review_id["edge-2"].asserted_currentness == "unspecified"
    assert all(
        edge.currentness_review_source == "llm"
        for edge in result.edges_by_review_id.values()
    )
    assert "2026-08-20T00:00:00+00:00" in call_llm.call_args.args[0]


def test_failed_review_leaves_edge_unreviewed() -> None:
    result = review_resolved_edge_currentness(
        items=(_item("edge-1"),),
        reference_at=datetime(2026, 8, 20, tzinfo=UTC),
        model="test-model",
        model_config_id=None,
        call_llm=MagicMock(side_effect=TimeoutError("model timeout")),
    )

    assert result.edges_by_review_id == {}
    assert result.counts.failed_requests == 1
    assert result.counts.missing_decisions == 1
    assert result.counts.reviewed == 0
