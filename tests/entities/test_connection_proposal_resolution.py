"""Tests for global automatic-connection proposal resolution."""

from __future__ import annotations

from backfield_entities.connections.postprocess import resolve_auto_connection_proposals
from backfield_entities.connections.types import (
    AutoConnectionCandidatePair,
    AutoConnectionEdgeProposal,
    LinkedEntitySnapshot,
    PairEvidencePacket,
)


def _candidate(
    candidate_id: str = "candidate-1",
    *,
    from_id: str = "person-1",
    to_id: str = "org-1",
    from_type: str = "person",
    to_type: str = "organization",
    score: int = 40,
) -> AutoConnectionCandidatePair:
    return AutoConnectionCandidatePair(
        candidate_id=candidate_id,
        from_entity=LinkedEntitySnapshot(
            entity_type=from_type,
            substrate_id=1,
            canonical_id=from_id,
            label="From",
        ),
        to_entity=LinkedEntitySnapshot(
            entity_type=to_type,
            substrate_id=2,
            canonical_id=to_id,
            label="To",
        ),
        evidence=PairEvidencePacket(
            snippets=("From has a relationship with To.",),
            source="same_sentence",
            score=score,
        ),
    )


def _edge(
    nature: str,
    *,
    candidate_id: str = "candidate-1",
    from_id: str = "person-1",
    to_id: str = "org-1",
    confidence: float = 0.95,
    quote: str = "From has a relationship with To.",
) -> AutoConnectionEdgeProposal:
    return AutoConnectionEdgeProposal(
        candidate_id=candidate_id,
        from_entity_id=from_id,
        to_entity_id=to_id,
        description=f"From {nature} To.",
        nature=nature,
        confidence=confidence,
        quote=quote,
    )


def test_exact_duplicates_choose_strongest_evidence() -> None:
    weak = _candidate("weak", score=30)
    strong = _candidate("strong", score=40)
    result = resolve_auto_connection_proposals(
        [
            _edge("works_for", candidate_id="weak", confidence=0.99),
            _edge("works_for", candidate_id="strong", confidence=0.95),
        ],
        candidates={"weak": weak, "strong": strong},
    )

    assert len(result.edges) == 1
    assert result.edges[0].candidate_id == "strong"
    assert result.stats.exact_duplicates == 1


def test_specific_nature_subsumes_broader_natures() -> None:
    candidate = _candidate()
    result = resolve_auto_connection_proposals(
        [_edge("leads"), _edge("works_for"), _edge("member_of")],
        candidates={candidate.candidate_id: candidate},
    )

    assert [edge.nature for edge in result.edges] == ["leads"]
    assert result.stats.subsumed == 2


def test_independent_natures_coexist() -> None:
    candidate = _candidate()
    result = resolve_auto_connection_proposals(
        [_edge("founded"), _edge("leads")],
        candidates={candidate.candidate_id: candidate},
    )

    assert {edge.nature for edge in result.edges} == {"founded", "leads"}


def test_ambiguous_explicit_conflict_writes_neither() -> None:
    candidate = _candidate(
        from_type="person",
        to_type="person",
        from_id="person-1",
        to_id="person-2",
    )
    result = resolve_auto_connection_proposals(
        [
            _edge("supports", from_id="person-1", to_id="person-2", confidence=0.95),
            _edge("opposes", from_id="person-1", to_id="person-2", confidence=0.96),
        ],
        candidates={candidate.candidate_id: candidate},
    )

    assert result.edges == ()
    assert result.stats.ambiguous_conflicts == 1


def test_symmetric_natures_use_stable_endpoint_order() -> None:
    candidate = _candidate(
        from_type="person",
        to_type="person",
        from_id="person-z",
        to_id="person-a",
    )
    result = resolve_auto_connection_proposals(
        [
            _edge(
                "spouse_of",
                from_id="person-z",
                to_id="person-a",
            )
        ],
        candidates={candidate.candidate_id: candidate},
    )

    assert result.edges[0].from_entity_id == "person-a"
    assert result.edges[0].to_entity_id == "person-z"
