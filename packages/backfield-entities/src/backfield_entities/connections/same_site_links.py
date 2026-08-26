"""Deterministic organization→location edges for same-site name overlap."""

from __future__ import annotations

from backfield_entities.connections.match_tokens import org_location_site_names_match
from backfield_entities.connections.snippets import (
    collect_entity_pair_text_evidence,
    quote_is_supported,
)
from backfield_entities.connections.taxonomy import AUTO_CONNECTION_MIN_CONFIDENCE
from backfield_entities.connections.types import AutoConnectionEdgeProposal, LinkedEntitySnapshot
from backfield_entities.connections.validation import validate_auto_connection_candidate

# Org types that should not receive automatic same-site place links.
SAME_SITE_EXCLUDED_ORG_TYPES: frozenset[str] = frozenset(
    {
        "school_district",
        "government",
        "law_enforcement",
        "legislative_body",
        "political_party",
        "court",
        "sports_league",
        "media",
        "utilities",
        "public_health",
    }
)


def org_type_eligible_for_same_site(organization_type: str | None) -> bool:
    org_type = (organization_type or "").strip().lower()
    if not org_type:
        return True
    return org_type not in SAME_SITE_EXCLUDED_ORG_TYPES


def infer_same_site_org_location_edges(
    *,
    organizations: tuple[LinkedEntitySnapshot, ...],
    locations: tuple[LinkedEntitySnapshot, ...],
    article_text: str,
) -> tuple[AutoConnectionEdgeProposal, ...]:
    """Link organizations to place canonicals that name the same physical site."""
    if not organizations or not locations:
        return ()

    edges: list[AutoConnectionEdgeProposal] = []
    seen: set[tuple[str, str]] = set()

    for org in organizations:
        if not org_type_eligible_for_same_site(org.organization_type):
            continue
        for location in locations:
            matched, match_basis = org_location_site_names_match(org.label, location.label)
            if not matched:
                continue
            key = (org.canonical_id, location.canonical_id)
            if key in seen:
                continue
            pair_snippets = collect_entity_pair_text_evidence(
                org,
                location,
                article_text,
            )
            if not pair_snippets:
                continue
            quote = pair_snippets[0]
            proposal = AutoConnectionEdgeProposal(
                from_entity_id=org.canonical_id,
                to_entity_id=location.canonical_id,
                description=f"{org.label} is located at {location.label}.",
                nature="located_at",
                confidence=AUTO_CONNECTION_MIN_CONFIDENCE,
                quote=quote,
                reason="Organization and place canonicals share the same site name.",
                match_basis=match_basis,
            )
            validation = validate_auto_connection_candidate(
                from_entity_type="organization",
                to_entity_type="location",
                description=proposal.description,
                nature=proposal.nature,
                confidence=float(proposal.confidence),
                quote=proposal.quote,
                location_type=location.location_type,
            )
            if not validation.ok:
                continue
            if not quote_is_supported(
                proposal.quote,
                article_text=article_text,
                from_entity=org,
                to_entity=location,
                pair_snippets=pair_snippets,
            ):
                continue
            seen.add(key)
            edges.append(proposal)

    return tuple(edges)
