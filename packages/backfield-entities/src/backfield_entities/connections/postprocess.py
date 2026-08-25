"""Post-processing rules for proposed automatic connections."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from backfield_entities.connections.natures import (
    NATURE_CONFLICTS,
    NATURE_SUBSUMPTIONS,
    nature_def,
    normalize_preferred_nature_slug,
)
from backfield_entities.connections.types import (
    AutoConnectionCandidatePair,
    AutoConnectionEdgeProposal,
)

CONFLICT_CONFIDENCE_MARGIN = 0.05
CONFLICT_EVIDENCE_SCORE_MARGIN = 10


@dataclass(frozen=True)
class ProposalResolutionStats:
    exact_duplicates: int = 0
    subsumed: int = 0
    conflicts_resolved: int = 0
    ambiguous_conflicts: int = 0
    self_loops: int = 0
    invalid_candidates: int = 0


@dataclass(frozen=True)
class ProposalResolutionResult:
    edges: tuple[AutoConnectionEdgeProposal, ...]
    stats: ProposalResolutionStats


def _candidate_types(
    edge: AutoConnectionEdgeProposal,
    candidate: AutoConnectionCandidatePair,
) -> tuple[str, str]:
    if edge.from_entity_id == candidate.from_entity.canonical_id:
        return candidate.from_entity_type, candidate.to_entity_type
    return candidate.to_entity_type, candidate.from_entity_type


def _normalize_edge(
    edge: AutoConnectionEdgeProposal,
    candidate: AutoConnectionCandidatePair,
) -> AutoConnectionEdgeProposal:
    nature = normalize_preferred_nature_slug(edge.nature)
    from_type, to_type = _candidate_types(edge, candidate)
    definition = nature_def(nature, from_type, to_type) if nature else None
    from_id = edge.from_entity_id
    to_id = edge.to_entity_id
    if definition is not None and definition.symmetric and to_id < from_id:
        from_id, to_id = to_id, from_id
    return edge.model_copy(
        update={
            "from_entity_id": from_id,
            "to_entity_id": to_id,
            "nature": nature,
        }
    )


def _proposal_rank(
    edge: AutoConnectionEdgeProposal,
    candidates: dict[str, AutoConnectionCandidatePair],
) -> tuple[int, float, int, str]:
    candidate = candidates.get(edge.candidate_id or "")
    evidence_score = candidate.evidence.score if candidate is not None else 50
    return (
        evidence_score,
        float(edge.confidence),
        len(edge.quote.strip()),
        edge.candidate_id or "",
    )


def _is_standalone_proposal(edge: AutoConnectionEdgeProposal) -> bool:
    """Affiliation and other non-LLM proposals without a candidate packet."""
    return not edge.candidate_id and bool(
        edge.from_entity_id and edge.to_entity_id and edge.nature
    )


def _normalize_standalone_edge(
    edge: AutoConnectionEdgeProposal,
) -> AutoConnectionEdgeProposal:
    return edge.model_copy(update={"nature": normalize_preferred_nature_slug(edge.nature)})


def _conflict_winner(
    left: AutoConnectionEdgeProposal,
    right: AutoConnectionEdgeProposal,
    candidates: dict[str, AutoConnectionCandidatePair],
) -> AutoConnectionEdgeProposal | None:
    confidence_gap = abs(float(left.confidence) - float(right.confidence))
    left_candidate = candidates.get(left.candidate_id or "")
    right_candidate = candidates.get(right.candidate_id or "")
    left_score = left_candidate.evidence.score if left_candidate is not None else 0
    right_score = right_candidate.evidence.score if right_candidate is not None else 0
    score_gap = abs(left_score - right_score)
    if (
        confidence_gap < CONFLICT_CONFIDENCE_MARGIN
        and score_gap < CONFLICT_EVIDENCE_SCORE_MARGIN
    ):
        return None
    return max((left, right), key=lambda edge: _proposal_rank(edge, candidates))


def resolve_auto_connection_proposals(
    edges: list[AutoConnectionEdgeProposal],
    *,
    candidates: dict[str, AutoConnectionCandidatePair],
) -> ProposalResolutionResult:
    """Normalize and resolve all proposals from one inference pass."""
    exact_duplicates = 0
    subsumed = 0
    conflicts_resolved = 0
    ambiguous_conflicts = 0
    self_loops = 0
    invalid_candidates = 0

    deduped: dict[tuple[str, str, str], AutoConnectionEdgeProposal] = {}
    for edge in edges:
        candidate = candidates.get(edge.candidate_id or "")
        if candidate is None:
            if not _is_standalone_proposal(edge):
                invalid_candidates += 1
                continue
            normalized = _normalize_standalone_edge(edge)
        else:
            normalized = _normalize_edge(edge, candidate)
        if normalized.from_entity_id == normalized.to_entity_id:
            self_loops += 1
            continue
        key = (
            normalized.from_entity_id,
            normalized.to_entity_id,
            normalized.nature or "",
        )
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = normalized
            continue
        exact_duplicates += 1
        deduped[key] = max(
            (existing, normalized),
            key=lambda proposal: _proposal_rank(proposal, candidates),
        )

    grouped: dict[tuple[str, str], list[AutoConnectionEdgeProposal]] = defaultdict(list)
    for edge in deduped.values():
        grouped[(edge.from_entity_id, edge.to_entity_id)].append(edge)

    resolved: list[AutoConnectionEdgeProposal] = []
    for pair_edges in grouped.values():
        natures = {edge.nature for edge in pair_edges if edge.nature}
        suppressed: set[str] = set()
        for specific in natures:
            suppressed.update(NATURE_SUBSUMPTIONS.get(specific, frozenset()) & natures)
        filtered = [edge for edge in pair_edges if edge.nature not in suppressed]
        subsumed += len(pair_edges) - len(filtered)

        rejected: set[int] = set()
        for conflict in NATURE_CONFLICTS:
            conflict_edges = [edge for edge in filtered if edge.nature in conflict]
            if len(conflict_edges) < 2:
                continue
            left, right = conflict_edges[:2]
            winner = _conflict_winner(left, right, candidates)
            if winner is None:
                rejected.update({id(left), id(right)})
                ambiguous_conflicts += 1
            else:
                loser = right if winner is left else left
                rejected.add(id(loser))
                conflicts_resolved += 1
        resolved.extend(edge for edge in filtered if id(edge) not in rejected)

    resolved.sort(
        key=lambda edge: (
            edge.from_entity_id,
            edge.to_entity_id,
            edge.nature or "",
            edge.candidate_id or "",
        )
    )
    return ProposalResolutionResult(
        edges=tuple(resolved),
        stats=ProposalResolutionStats(
            exact_duplicates=exact_duplicates,
            subsumed=subsumed,
            conflicts_resolved=conflicts_resolved,
            ambiguous_conflicts=ambiguous_conflicts,
            self_loops=self_loops,
            invalid_candidates=invalid_candidates,
        ),
    )


def apply_subsumption_rules(
    edges: list[AutoConnectionEdgeProposal],
) -> list[AutoConnectionEdgeProposal]:
    """Drop redundant natures for the same canonical pair in one run."""
    grouped: dict[tuple[str, str], list[AutoConnectionEdgeProposal]] = defaultdict(list)
    for edge in edges:
        grouped[(edge.from_entity_id, edge.to_entity_id)].append(edge)

    out: list[AutoConnectionEdgeProposal] = []
    for group in grouped.values():
        natures = {edge.nature for edge in group if edge.nature}
        filtered = list(group)
        if "leads" in natures and "works_for" in natures:
            filtered = [edge for edge in filtered if edge.nature != "works_for"]
        if "located_at" in natures and "based_in" in natures:
            filtered = [edge for edge in filtered if edge.nature != "based_in"]
        if "plays_for" in natures and "member_of" in natures:
            filtered = [edge for edge in filtered if edge.nature != "member_of"]
        if "coaches" in natures and "works_for" in natures:
            filtered = [edge for edge in filtered if edge.nature != "works_for"]
        if "holds_office_in" in natures and "represents" in natures:
            # Prefer office-holding over district representation when both proposed.
            filtered = [edge for edge in filtered if edge.nature != "represents"]
        out.extend(filtered)
    return out
