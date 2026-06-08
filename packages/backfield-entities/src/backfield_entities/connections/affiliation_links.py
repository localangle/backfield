"""Deterministic person→organization edges from extracted affiliation fields."""

from __future__ import annotations

from backfield_entities.connections.match_tokens import (
    organization_match_tokens,
    person_affiliation_matches_organization_label,
)
from backfield_entities.connections.snippets import quote_is_supported
from backfield_entities.connections.taxonomy import AUTO_CONNECTION_MIN_CONFIDENCE
from backfield_entities.connections.types import AutoConnectionEdgeProposal, LinkedEntitySnapshot
from backfield_entities.connections.validation import validate_auto_connection_candidate


def _nature_for_affiliation_link(org: LinkedEntitySnapshot) -> str:
    if (org.organization_type or "").strip().lower() == "sports_team":
        return "member_of"
    return "works_for"


def _select_affiliation_quote(
    *,
    person: LinkedEntitySnapshot,
    org: LinkedEntitySnapshot,
    article_text: str,
) -> str | None:
    team_tokens = organization_match_tokens(org.label)
    if person.affiliation:
        team_tokens = tuple(
            dict.fromkeys((*team_tokens, *organization_match_tokens(person.affiliation)))
        )
    person_label = person.label.strip()
    if not person_label:
        return None

    for snippet in person.snippets:
        lower = snippet.lower()
        if person_label.lower() not in lower:
            continue
        if any(token in lower for token in team_tokens):
            return snippet.strip()

    haystack = article_text or ""
    idx = haystack.find(person_label)
    if idx < 0:
        return None
    window_start = max(0, idx - 120)
    window_end = min(len(haystack), idx + len(person_label) + 180)
    window = haystack[window_start:window_end]
    lower_window = window.lower()
    if any(token in lower_window for token in team_tokens):
        return window.strip()
    return None


def infer_affiliation_person_organization_edges(
    *,
    people: tuple[LinkedEntitySnapshot, ...],
    organizations: tuple[LinkedEntitySnapshot, ...],
    article_text: str,
) -> tuple[AutoConnectionEdgeProposal, ...]:
    """Link people to organizations when affiliation names the org (incl. team nicknames)."""
    if not people or not organizations:
        return ()

    edges: list[AutoConnectionEdgeProposal] = []
    seen: set[tuple[str, str, str]] = set()

    for person in people:
        if not person.affiliation:
            continue
        for org in organizations:
            if not person_affiliation_matches_organization_label(person.affiliation, org.label):
                continue
            nature = _nature_for_affiliation_link(org)
            key = (person.canonical_id, org.canonical_id, nature)
            if key in seen:
                continue
            quote = _select_affiliation_quote(
                person=person,
                org=org,
                article_text=article_text,
            )
            if not quote:
                continue
            proposal = AutoConnectionEdgeProposal(
                from_entity_id=person.canonical_id,
                to_entity_id=org.canonical_id,
                nature=nature,
                confidence=AUTO_CONNECTION_MIN_CONFIDENCE,
                quote=quote,
                reason="Person affiliation matches organization label.",
            )
            validation = validate_auto_connection_candidate(
                from_entity_type="person",
                to_entity_type="organization",
                nature=proposal.nature,
                confidence=float(proposal.confidence),
                quote=proposal.quote,
            )
            if not validation.ok:
                continue
            if not quote_is_supported(
                proposal.quote,
                article_text=article_text,
                from_entity=person,
                to_entity=org,
                pair_snippets=(quote,),
            ):
                continue
            seen.add(key)
            edges.append(proposal)

    return tuple(edges)
