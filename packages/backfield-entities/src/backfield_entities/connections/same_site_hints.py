"""Same-site org↔location candidate discovery (hint-only; LLM confirms)."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_entities.connections.match_tokens import head_name_segment
from backfield_entities.connections.snippets import collect_pair_snippets_for_entities
from backfield_entities.connections.types import LinkedEntitySnapshot

# Single-site orgs that commonly share a PlaceExtract ``place`` label.
SAME_SITE_ELIGIBLE_ORG_TYPES: frozenset[str] = frozenset(
    {
        "school",
        "hospital",
        "university",
        "local_business",
        "company",
        "nonprofit",
        "religious_org",
        "culture_arts",
        "community_group",
        "public_services",
        "real_estate",
        "financial_institution",
        "other",
    }
)

SAME_SITE_EXCLUDED_ORG_TYPES: frozenset[str] = frozenset(
    {
        "school_district",
        "government",
        "law_enforcement",
        "legislative_body",
        "political_party",
        "court",
        "sports_team",
        "sports_league",
        "media",
        "utilities",
        "public_health",
    }
)

_MIN_HEAD_NAME_LEN = 4
_MATCH_BASIS = "head_name_match"


@dataclass(frozen=True)
class SameSiteOrgLocationHint:
    org: LinkedEntitySnapshot
    location: LinkedEntitySnapshot
    match_basis: str
    suggested_snippets: tuple[str, ...]


def _org_type_eligible(organization_type: str | None) -> bool:
    org_type = (organization_type or "").strip().lower()
    if not org_type:
        return False
    if org_type in SAME_SITE_EXCLUDED_ORG_TYPES:
        return False
    return org_type in SAME_SITE_ELIGIBLE_ORG_TYPES


def head_names_match(org_label: str, location_label: str) -> bool:
    """True when org and location share the same primary (pre-comma) name."""
    org_head = head_name_segment(org_label)
    loc_head = head_name_segment(location_label)
    if len(org_head) < _MIN_HEAD_NAME_LEN or len(loc_head) < _MIN_HEAD_NAME_LEN:
        return False
    return org_head == loc_head


def discover_same_site_org_location_hints(
    *,
    organizations: tuple[LinkedEntitySnapshot, ...],
    locations: tuple[LinkedEntitySnapshot, ...],
    article_text: str,
) -> tuple[SameSiteOrgLocationHint, ...]:
    """Return hint pairs for the org→location LLM pass (no edges are written here)."""
    if not organizations or not locations:
        return ()

    hints: list[SameSiteOrgLocationHint] = []
    seen: set[tuple[str, str]] = set()

    for org in organizations:
        if not _org_type_eligible(org.organization_type):
            continue
        for location in locations:
            if not head_names_match(org.label, location.label):
                continue
            key = (org.canonical_id, location.canonical_id)
            if key in seen:
                continue
            snippets = collect_pair_snippets_for_entities(
                left=org,
                right=location,
                article_text=article_text,
            )
            if not snippets:
                continue
            seen.add(key)
            hints.append(
                SameSiteOrgLocationHint(
                    org=org,
                    location=location,
                    match_basis=_MATCH_BASIS,
                    suggested_snippets=snippets,
                )
            )

    return tuple(hints)
