"""Deterministic person→organization edges from extracted affiliation fields."""

from __future__ import annotations

from backfield_entities.connections.match_tokens import (
    person_affiliation_matches_organization_label,
)
from backfield_entities.connections.snippets import quote_is_supported
from backfield_entities.connections.taxonomy import AUTO_CONNECTION_MIN_CONFIDENCE
from backfield_entities.connections.types import AutoConnectionEdgeProposal, LinkedEntitySnapshot
from backfield_entities.connections.validation import validate_auto_connection_candidate


def _nature_for_affiliation_link(
    person: LinkedEntitySnapshot,
    org: LinkedEntitySnapshot,
) -> str:
    if (org.organization_type or "").strip().lower() == "sports_team":
        person_type = (person.person_type or "").strip().lower()
        if person_type in {"athlete", "coach", "player"}:
            return "member_of"
        return "works_for"
    return "works_for"


def _select_affiliation_quote(
    *,
    person: LinkedEntitySnapshot,
    org: LinkedEntitySnapshot,
    article_text: str,
) -> str | None:
    """Evidence for an affiliation link: where the person appears in the story.

    Called only after ``person_affiliation_matches_organization_label`` succeeds, so the
    affiliation field (not prose team nicknames) is the link basis. The quote cites the
    person in context; it does not re-require the organization name in the same span.
    """
    _ = org
    person_label = person.label.strip()
    if not person_label:
        return None
    label_lower = person_label.lower()

    for snippet in person.snippets:
        if label_lower in snippet.lower():
            return snippet.strip()

    haystack = article_text or ""
    idx = haystack.lower().find(label_lower)
    if idx < 0:
        return None
    window_start = max(0, idx - 120)
    window_end = min(len(haystack), idx + len(person_label) + 180)
    return haystack[window_start:window_end].strip()


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
            nature = _nature_for_affiliation_link(person, org)
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
