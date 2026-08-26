"""Token helpers for co-mention windows and affiliation matching."""

from __future__ import annotations

from backfield_entities.entities.organization.types import normalize_organization_text


def organization_match_tokens(label: str | None) -> tuple[str, ...]:
    """Searchable normalized tokens for an organization label (nickname + full form)."""
    norm = normalize_organization_text(label)
    if not norm:
        return ()
    tokens: list[str] = [norm]
    parts = norm.split()
    if len(parts) > 1:
        last = parts[-1]
        if last and last not in tokens:
            tokens.append(last)
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return tuple(out)


# Markers that distinguish school/prep team labels from pro clubs headed by a city
# ("Chicago Cubs") so short affiliations like "Montini" can prefix-match safely.
_SCHOOL_OR_PREP_TEAM_MARKERS = (
    "high school",
    "academy",
    "preparatory",
    "football team",
    "basketball team",
    "baseball team",
    "softball team",
    "soccer team",
    "volleyball team",
    "lacrosse team",
    "hockey team",
    "wrestling team",
)


def _looks_like_school_or_prep_team(org_label: str) -> bool:
    return any(marker in org_label for marker in _SCHOOL_OR_PREP_TEAM_MARKERS)


def person_affiliation_matches_organization_label(
    affiliation: str | None,
    organization_label: str | None,
) -> bool:
    """True when a person's affiliation clearly names the organization."""
    aff = normalize_organization_text(affiliation)
    org_label = normalize_organization_text(organization_label)
    if not aff or not org_label:
        return False
    if aff == org_label:
        return True
    org_parts = org_label.split()
    if len(org_parts) > 1 and aff == org_parts[-1]:
        # Team nickname before player name (e.g. Phillies → Philadelphia Phillies).
        return True
    # School short name: Montini → Montini Catholic High School boys football team.
    # Require school/prep markers so bare cities do not match pro clubs (Chicago ↛ Cubs).
    if (
        len(aff) >= 4
        and org_label.startswith(f"{aff} ")
        and _looks_like_school_or_prep_team(org_label)
    ):
        return True
    return False


def head_name_segment(label: str | None) -> str:
    """Primary name before the first comma (normalized)."""
    if not label:
        return ""
    return normalize_organization_text(str(label).split(",")[0])


_MIN_SITE_NAME_LEN = 4
MATCH_BASIS_SITE_NAME_EXACT = "site_name_exact"
MATCH_BASIS_ORG_AT_NAMED_PLACE = "org_at_named_place"


def head_name_tokens(label: str | None) -> tuple[str, ...]:
    """Normalized tokens from the primary (pre-comma) label segment."""
    head = head_name_segment(label)
    if not head:
        return ()
    return tuple(head.split())


def org_location_site_names_match(
    org_label: str,
    location_label: str,
) -> tuple[bool, str]:
    """True when an org and place canonical clearly name the same site.

    The place head must be a contiguous token prefix of the org head (or equal).
    Single-token place names require an exact token-sequence match so city names
    do not absorb unrelated orgs (Chicago Public Schools ↮ Chicago).
    """
    org_tokens = head_name_tokens(org_label)
    loc_tokens = head_name_tokens(location_label)
    if not org_tokens or not loc_tokens:
        return False, ""

    loc_head = " ".join(loc_tokens)
    if len(loc_head) < _MIN_SITE_NAME_LEN:
        return False, ""

    if org_tokens == loc_tokens:
        return True, MATCH_BASIS_SITE_NAME_EXACT

    if len(loc_tokens) == 1:
        return False, ""

    if len(org_tokens) > len(loc_tokens) and org_tokens[: len(loc_tokens)] == loc_tokens:
        return True, MATCH_BASIS_ORG_AT_NAMED_PLACE

    return False, ""


def location_comention_tokens(label: str | None) -> tuple[str, ...]:
    """Search tokens for a location label (head name + optional neighborhood segment)."""
    tokens: list[str] = []
    tokens.extend(organization_match_tokens(head_name_segment(label)))
    if not label:
        return _dedupe_tokens(tokens)
    parts = [part.strip() for part in str(label).split(",")]
    if len(parts) >= 2:
        neighborhood = normalize_organization_text(parts[1])
        if neighborhood:
            tokens.append(neighborhood)
    return _dedupe_tokens(tokens)


def _dedupe_tokens(tokens: list[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return tuple(out)


def entity_comention_tokens(
    *,
    label: str | None,
    affiliation: str | None = None,
    entity_type: str | None = None,
) -> tuple[str, ...]:
    """Case-folded tokens used to detect co-mentions in article windows."""
    if (entity_type or "").strip().lower() == "location":
        return location_comention_tokens(label)
    tokens: list[str] = []
    for source in (label, affiliation):
        tokens.extend(organization_match_tokens(source))
    return _dedupe_tokens(tokens)
