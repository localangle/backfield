"""Regression tests for exact-or-absent entity occurrence spans."""

from __future__ import annotations

import pytest
from backfield_entities.occurrence_spans import find_proven_occurrence_span


@pytest.mark.parametrize(
    ("article", "evidence", "expected_slice"),
    [
        ("Before City Hall after.", "City Hall", "City Hall"),
        ("Before City\u00a0Hall after.", "City Hall", "City\u00a0Hall"),
        ("Before Citya0Hall after.", "City Hall", "Citya0Hall"),
        ('She said “hello” today.', 'She said "hello" today.', "She said “hello” today."),
        ("The council met", "The council met.", "The council met"),
        ("The Ｃity Hall opened.", "The City Hall opened.", "The Ｃity Hall opened."),
    ],
)
def test_find_proven_occurrence_span_maps_normalized_evidence_to_article_offsets(
    article: str,
    evidence: str,
    expected_slice: str,
) -> None:
    span = find_proven_occurrence_span(
        article_text=article,
        evidence_texts=(evidence,),
    )

    assert span is not None
    assert article[slice(*span)] == expected_slice


def test_find_proven_occurrence_span_rejects_paraphrase_and_truncated_overlap() -> None:
    article = "The council approved the budget after a long debate."
    evidence = "The council unanimously rejected the budget after testimony from residents."

    assert (
        find_proven_occurrence_span(
            article_text=article,
            evidence_texts=(evidence,),
        )
        is None
    )


def test_find_proven_occurrence_span_rejects_bad_offsets_but_finds_exact_evidence() -> None:
    article = "Unrelated opening. Jane Doe spoke."

    span = find_proven_occurrence_span(
        article_text=article,
        evidence_texts=("Jane Doe",),
        proposed_span=(0, 9),
    )

    assert span is not None
    assert article[slice(*span)] == "Jane Doe"


def test_find_proven_occurrence_span_returns_none_when_offsets_and_evidence_are_wrong() -> None:
    article = "Unrelated opening."

    assert (
        find_proven_occurrence_span(
            article_text=article,
            evidence_texts=("Jane Doe spoke at length.",),
            proposed_span=(0, len(article)),
        )
        is None
    )
