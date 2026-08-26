"""Deterministic person→organization edges from extracted affiliation fields."""

from __future__ import annotations

from backfield_entities.connections.match_tokens import (
    person_affiliation_matches_organization_label,
)
from backfield_entities.connections.taxonomy import AUTO_CONNECTION_MIN_CONFIDENCE
from backfield_entities.connections.types import AutoConnectionEdgeProposal, LinkedEntitySnapshot
from backfield_entities.connections.validation import validate_auto_connection_candidate


def _nature_for_affiliation_link(
    person: LinkedEntitySnapshot,
    org: LinkedEntitySnapshot,
) -> str:
    if (org.organization_type or "").strip().lower() == "sports_team":
        person_type = (person.person_type or "").strip().lower()
        if person_type == "coach":
            return "coaches"
        if person_type in {"athlete", "player"}:
            return "plays_for"
        return "works_for"
    return "works_for"


def _affiliation_edge_description(
    person: LinkedEntitySnapshot,
    org: LinkedEntitySnapshot,
    *,
    nature: str,
) -> str:
    if nature == "plays_for":
        return f"{person.label} plays for {org.label}."
    if nature == "coaches":
        return f"{person.label} coaches {org.label}."
    if nature == "works_for":
        return f"{person.label} works for {org.label}."
    return f"{person.label} is affiliated with {org.label}."


def _select_affiliation_quote(
    *,
    person: LinkedEntitySnapshot,
    article_text: str,
) -> str | None:
    """Evidence for an affiliation link: where the person appears in the story.

    Called only after ``person_affiliation_matches_organization_label`` succeeds, so the
    affiliation field (not prose team nicknames) is the link basis. The quote cites the
    person in context; it does not re-require the organization name in the same span.
    """
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
                article_text=article_text,
            )
            if not quote:
                continue
            proposal = AutoConnectionEdgeProposal(
                from_entity_id=person.canonical_id,
                to_entity_id=org.canonical_id,
                description=_affiliation_edge_description(person, org, nature=nature),
                nature=nature,
                confidence=AUTO_CONNECTION_MIN_CONFIDENCE,
                quote=quote,
                reason="Extracted affiliation matches organization label.",
                match_basis="affiliation_match",
            )
            validation = validate_auto_connection_candidate(
                from_entity_type="person",
                to_entity_type="organization",
                description=proposal.description,
                nature=proposal.nature,
                confidence=float(proposal.confidence),
                quote=proposal.quote,
            )
            if not validation.ok:
                continue
            seen.add(key)
            edges.append(proposal)

    return tuple(edges)
