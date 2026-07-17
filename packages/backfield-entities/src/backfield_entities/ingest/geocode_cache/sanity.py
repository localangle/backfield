"""Sanity gates for geocode cache hits (tier 1 canonical, tier 2 substrate cache, adjudication)."""

from __future__ import annotations

import re
from typing import Any

from backfield_entities.canonical.jurisdiction import (
    jurisdiction_from_components,
    parse_jurisdiction_from_formatted_address,
)
from backfield_entities.canonical.link_matrix import (
    autolink_container_to_fine_denied,
    link_pair_allowed,
)
from backfield_entities.ingest.geocode_cache.fingerprint import normalize_substrate_cache_query

# Fine-grained PlaceExtract rows must not autolink to container admin canonicals via cache.
_FINE_SUBSTRATE_TYPES: frozenset[str] = frozenset(
    {
        "address",
        "place",
        "point",
        "intersection_road",
        "intersection_highway",
    }
)
_CONTAINER_CANONICAL_TYPES: frozenset[str] = frozenset(
    {
        "city",
        "town",
        "village",
        "county",
        "state",
        "region_state",
        "region_national",
        "country",
    }
)
_INTERSECTION_SUBSTRATE_TYPES: frozenset[str] = frozenset(
    {"intersection_road", "intersection_highway"}
)
_STREET_SUBSTRATE_TYPES: frozenset[str] = frozenset({"street_road"})
_POI_LIKE_CANONICAL_TYPES: frozenset[str] = frozenset({"place", "point", "neighborhood"})
# Exclude political_district: number/kind identity is authoritative; ordinal vs
# numeral heads (Eighth Ward vs Ward 8) are too brittle for a string head gate.
_ADMIN_PROPER_HEAD_TYPES: frozenset[str] = frozenset(
    {
        "neighborhood",
        "city",
        "town",
        "village",
        "county",
        "community_area",
        "borough",
        "suburb",
        "district",
        "ward",
        "region_city",
    }
)

_HOUSE_NUMBER_RE = re.compile(r"\d")
_HOUSE_NUMBER_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])(\d+[A-Za-z]?)(?![A-Za-z0-9])")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_INTERSECTION_AND_RE = re.compile(r"\s+(?:and|&)\s+", re.IGNORECASE)
_DIRECTION_PREFIX = frozenset({"n", "north", "s", "south", "e", "east", "w", "west"})
_NAMED_POI_TYPES: frozenset[str] = frozenset({"place", "point", "natural"})


def autolink_fine_substrate_to_container_canonical_denied(
    substrate_lt: str | None,
    canonical_lt: str | None,
) -> bool:
    """True when a street/POI substrate row must not cache-hit a city-or-coarser canonical."""
    s = (substrate_lt or "").strip().lower()
    c = (canonical_lt or "").strip().lower()
    return s in _FINE_SUBSTRATE_TYPES and c in _CONTAINER_CANONICAL_TYPES


def address_line_from_components(
    components: dict[str, Any] | None,
    location_text: str,
) -> str:
    """Best-effort street line from PlaceExtract components or query text."""
    c = components if isinstance(components, dict) else {}
    addr = str(c.get("address") or "").strip()
    if addr:
        return addr
    return str(location_text or "").strip()


def address_requests_street_resolution(addr_line: str) -> bool:
    """True when the extract expects a street- or building-level hit (not city-only)."""
    s = (addr_line or "").strip()
    if not s:
        return False
    if _HOUSE_NUMBER_RE.search(s):
        return True
    return len(s) >= 10


def _place_name_token(
    components: dict[str, Any] | None,
    location_text: str = "",
) -> str:
    c = components if isinstance(components, dict) else {}
    place = c.get("place")
    if isinstance(place, dict):
        name = str(place.get("name") or "").strip().lower()
        if name:
            return name
    raw = str(place or "").strip().lower()
    if raw:
        return raw
    first = str(location_text or "").split(",")[0]
    key = _compare_key(normalize_substrate_cache_query(first))
    tokens = [t for t in key.split() if t]
    if tokens and tokens[0] in _DIRECTION_PREFIX:
        tokens = tokens[1:]
    return " ".join(tokens)


def _meaningful_place_name_tokens(token: str) -> list[str]:
    return [t for t in (token or "").split() if len(t) >= 2]


_POI_TOKEN_CANONICAL_TYPES: frozenset[str] = frozenset(
    {
        "city",
        "town",
        "village",
        "place",
        "point",
        "neighborhood",
        "address",
        "region_state",
        "region_national",
        "county",
        "political_district",
    }
)
_POI_TOKEN_STRICT_CONTAINER_TYPES: frozenset[str] = frozenset(
    {
        "region_state",
        "region_national",
        "county",
        "political_district",
    }
)


def _label_contains_token(label: str, token: str) -> bool:
    t = (token or "").strip().lower()
    if len(t) < 2:
        return False
    return t in (label or "").strip().lower()


def _compare_key(text: str) -> str:
    """Loose key for substring checks (drops punctuation differences in street lines)."""
    return _NON_ALNUM_RE.sub(" ", (text or "").strip().lower()).strip()


def _identity_head_key(text: str) -> str:
    """Comparable first-segment key retaining every identity-bearing token."""
    head = _compare_key(normalize_substrate_cache_query(str(text or "").split(",")[0]))
    tokens = head.split()
    if len(tokens) > 1 and tokens[0] == "the":
        tokens = tokens[1:]
    return " ".join(tokens)


def named_location_heads_compatible(left: str, right: str) -> bool:
    """Accept punctuation/spacing variants without collapsing parent and child POIs."""
    left_head = _identity_head_key(left)
    right_head = _identity_head_key(right)
    if not left_head or not right_head:
        return False
    if left_head == right_head:
        return True
    return left_head.replace(" ", "") == right_head.replace(" ", "")


def canonical_location_self_consistency_blocked(
    *,
    status: str | None,
    location_type: str | None,
    label: str,
    formatted_address: str | None,
    country_code: str | None,
    subdivision_code: str | None,
    geometry_type: str | None,
    geometry_json: dict[str, Any] | None,
) -> bool:
    """True when a canonical contradicts its own lifecycle, jurisdiction, or geometry."""
    if (status or "").strip().lower() != "active":
        return True

    declared_geometry = (geometry_type or "").strip().lower()
    payload_geometry = (
        str(geometry_json.get("type") or "").strip().lower()
        if isinstance(geometry_json, dict)
        else ""
    )
    if declared_geometry and payload_geometry and declared_geometry != payload_geometry:
        return True

    address_country, address_subdivision = parse_jurisdiction_from_formatted_address(
        formatted_address
    )
    declared_country = (country_code or "").strip().upper()[:2] or None
    declared_subdivision = (subdivision_code or "").strip().upper()[:2] or None
    if declared_country and address_country and declared_country != address_country:
        return True
    if declared_subdivision and address_subdivision and declared_subdivision != address_subdivision:
        return True

    canonical_type = (location_type or "").strip().lower()
    address_head = _identity_head_key(str(formatted_address or ""))
    # A digit-leading formatted address is a street address, not a competing POI name.
    if (
        canonical_type in _NAMED_POI_TYPES
        and address_head
        and not address_head[0].isdigit()
        and not named_location_heads_compatible(label, str(formatted_address))
    ):
        return True
    return False


def substrate_canonical_jurisdiction_compatible(
    *,
    components: dict[str, Any] | None,
    canonical_country_code: str | None,
    canonical_subdivision_code: str | None,
) -> bool:
    """Require agreement whenever both substrate and canonical declare a jurisdiction."""
    substrate_country, substrate_subdivision, _city = jurisdiction_from_components(
        components if isinstance(components, dict) else {}
    )
    canonical_country = (canonical_country_code or "").strip().upper()[:2] or None
    canonical_subdivision = (canonical_subdivision_code or "").strip().upper()[:2] or None
    if substrate_country and canonical_country and substrate_country != canonical_country:
        return False
    if (
        substrate_subdivision
        and canonical_subdivision
        and substrate_subdivision != canonical_subdivision
    ):
        return False
    return True


def explicit_location_components_match_labels(
    *,
    components: dict[str, Any] | None,
    location_text: str,
    match_label: str,
    match_formatted_address: str | None = None,
) -> bool:
    """Require explicit jurisdiction, postal, and house-number evidence to agree."""
    comps = components if isinstance(components, dict) else {}
    labels = " ".join((str(match_label or ""), str(match_formatted_address or "")))
    expected_country, expected_subdivision, _city = jurisdiction_from_components(comps)
    resolved_country, resolved_subdivision = parse_jurisdiction_from_formatted_address(labels)
    if expected_country and resolved_country and expected_country != resolved_country:
        return False
    if (
        expected_subdivision
        and resolved_subdivision
        and expected_subdivision != resolved_subdivision
    ):
        return False

    postal = str(comps.get("postal_code") or "").strip()
    if postal:
        expected_postal = _compare_key(postal).replace(" ", "")
        resolved_blob = _compare_key(labels).replace(" ", "")
        if expected_postal and expected_postal not in resolved_blob:
            return False

    explicit_address = str(comps.get("address") or "").strip()
    requested_number = _HOUSE_NUMBER_TOKEN_RE.search(explicit_address)
    if explicit_address and requested_number is not None:
        candidate_numbers = {
            value.lower() for value in _HOUSE_NUMBER_TOKEN_RE.findall(labels)
        }
        if requested_number.group(1).lower() not in candidate_numbers:
            return False
    return True


def _leading_address_fragment(addr_line: str, *, max_len: int = 24) -> str:
    s = _compare_key(normalize_substrate_cache_query(addr_line))
    if not s:
        return ""
    return s[: min(max_len, len(s))]


def _address_fragment_in_labels(
    addr_line: str,
    *,
    labels: tuple[str, ...],
) -> bool:
    """True when a leading fragment of the address line appears in any candidate label."""
    frag = _leading_address_fragment(addr_line)
    if len(frag) < 8:
        return False
    for raw in labels:
        hay = _compare_key(normalize_substrate_cache_query(raw))
        if frag in hay:
            return True
    return False


def _street_name_head_tokens(text: str) -> list[str]:
    """Tokens of the street-name segment before the first comma (ordinals preserved).

    The street name (``62nd Street``, ``Archer Avenue``) is the part that actually
    distinguishes one street from another; the trailing ``…, Chicago, IL`` tail and any
    neighborhood annotation are dropped so they cannot mask a mismatch.
    """
    first = str(text or "").split(",")[0]
    key = _compare_key(normalize_substrate_cache_query(first))
    return [t for t in key.split() if t]


def _street_heads_compatible(substrate_head: list[str], candidate_head: list[str]) -> bool:
    """True when one street-name head is a token-prefix of the other (token-equal counts).

    Token-prefix comparison keeps ``62nd Street`` from matching ``162nd Street`` while still
    treating ``Chicago Avenue`` and ``Chicago Avenue`` as the same street regardless of the
    neighborhood / city tail that was already stripped by :func:`_street_name_head_tokens`.
    """
    if not substrate_head or not candidate_head:
        return False
    shorter, longer = sorted((substrate_head, candidate_head), key=len)
    return longer[: len(shorter)] == shorter


def _intersection_arm_heads(text: str) -> list[list[str]]:
    """Token heads for each street arm of an intersection (text before the first comma)."""
    first = str(text or "").split(",")[0]
    key = _compare_key(normalize_substrate_cache_query(first))
    if not key:
        return []
    arms = _INTERSECTION_AND_RE.split(key)
    out: list[list[str]] = []
    for arm in arms:
        tokens = [t for t in arm.split() if t]
        if not tokens:
            continue
        if tokens[0] in _DIRECTION_PREFIX:
            tokens = tokens[1:]
        if tokens:
            out.append(tokens)
    return out


def _intersection_all_arms_compatible(
    substrate_arms: list[list[str]],
    candidate_arms: list[list[str]],
) -> bool:
    """True when every substrate arm has a compatible arm on the candidate."""
    if not substrate_arms or not candidate_arms:
        return False
    for sub_arm in substrate_arms:
        if not any(_street_heads_compatible(sub_arm, cand_arm) for cand_arm in candidate_arms):
            return False
    return True


def _intersection_matches_intersection_labels(
    substrate_arms: list[list[str]],
    labels: tuple[str, ...],
) -> bool:
    for raw in labels:
        cand_arms = _intersection_arm_heads(raw)
        if cand_arms and _intersection_all_arms_compatible(substrate_arms, cand_arms):
            return True
    return False


def _house_number_in_labels(addr_line: str, *, labels: tuple[str, ...]) -> bool:
    """When the address line has digits, require a digit in at least one label."""
    if not _HOUSE_NUMBER_RE.search(addr_line or ""):
        return True
    for raw in labels:
        if _HOUSE_NUMBER_RE.search(raw or ""):
            return True
    return False


def cache_hit_sane_for_substrate(
    *,
    substrate_location_type: str | None,
    location_text: str,
    components: dict[str, Any] | None,
    match_label: str,
    match_formatted_address: str | None = None,
    match_location_type: str | None = None,
    match_geometry_type: str | None = None,
) -> bool:
    """Return False when a cache match is too coarse or inconsistent for this extract row."""
    substrate_lt = (substrate_location_type or "").strip().lower() or None
    canon_lt = (match_location_type or "").strip().lower() or None

    if not link_pair_allowed(substrate_lt, canon_lt):
        return False
    if autolink_container_to_fine_denied(substrate_lt, canon_lt):
        return False
    if autolink_fine_substrate_to_container_canonical_denied(substrate_lt, canon_lt):
        return False

    labels = (
        str(match_label or ""),
        str(match_formatted_address or ""),
    )
    label_blob = " ".join(labels)
    if not explicit_location_components_match_labels(
        components=components,
        location_text=location_text,
        match_label=match_label,
        match_formatted_address=match_formatted_address,
    ):
        return False

    if substrate_lt == "address":
        addr_line = address_line_from_components(components, location_text)
        if not address_requests_street_resolution(addr_line):
            return True
        poi = _place_name_token(components, location_text)
        if canon_lt in _POI_LIKE_CANONICAL_TYPES:
            if len(poi) >= 2 and _label_contains_token(label_blob, poi):
                return True
            if not _address_fragment_in_labels(addr_line, labels=labels):
                return False
            if not _house_number_in_labels(addr_line, labels=labels):
                return False
            return True
        if not _address_fragment_in_labels(addr_line, labels=labels):
            return False
        if not _house_number_in_labels(addr_line, labels=labels):
            return False
        geom = (match_geometry_type or "").strip().lower()
        if geom == "polygon" and canon_lt in _CONTAINER_CANONICAL_TYPES:
            return False
        return True

    if substrate_lt in _INTERSECTION_SUBSTRATE_TYPES:
        line = str(location_text or "").strip()
        if len(line) < 8:
            return True
        if canon_lt in _CONTAINER_CANONICAL_TYPES | _POI_LIKE_CANONICAL_TYPES:
            if not _address_fragment_in_labels(line, labels=labels):
                return False
        else:
            arms = _intersection_arm_heads(line)
            if arms and canon_lt in _INTERSECTION_SUBSTRATE_TYPES:
                if not _intersection_matches_intersection_labels(arms, labels):
                    return False
        return True

    if substrate_lt in _STREET_SUBSTRATE_TYPES:
        # Street identity lives in the street name itself. Loose scoring under-weights it
        # (``62nd``/``111th`` both reduce to a short token; ``<X> Avenue, Chicago, IL`` all
        # share the city/state tail), so require the substrate street name to match the
        # candidate's. This blocks unrelated streets from autolinking or inheriting a wrong
        # canonical via a poisoned ingest alias.
        sub_head = _street_name_head_tokens(location_text)
        if not sub_head:
            return True
        for raw in labels:
            if _street_heads_compatible(sub_head, _street_name_head_tokens(raw)):
                return True
        return False

    if substrate_lt in ("place", "point"):
        token = _place_name_token(components, location_text)
        if len(token) >= 2 and canon_lt in _POI_TOKEN_CANONICAL_TYPES:
            if canon_lt in _POI_TOKEN_STRICT_CONTAINER_TYPES:
                if len(_meaningful_place_name_tokens(token)) < 2:
                    return True
            if canon_lt in _NAMED_POI_TYPES:
                if not named_location_heads_compatible(location_text, match_label):
                    return False
            elif not _label_contains_token(label_blob, token):
                return False
        return True

    if (
        substrate_lt in _ADMIN_PROPER_HEAD_TYPES
        and (canon_lt is None or canon_lt in _ADMIN_PROPER_HEAD_TYPES)
    ):
        # Neighborhood/admin identity lives in the leading placename. Block
        # Bucktown↔Uptown-style hits even when a poisoned alias or shared city/state
        # tail would otherwise score as an exact match.
        sub_head = _street_name_head_tokens(location_text)
        if sub_head:
            for raw in labels:
                if _street_heads_compatible(sub_head, _street_name_head_tokens(raw)):
                    return True
            return False

    return True


def substrate_canonical_link_blocked_by_content_sanity(
    *,
    substrate_location_type: str | None,
    location_text: str,
    components: dict[str, Any] | None,
    match_label: str,
    match_formatted_address: str | None = None,
    match_location_type: str | None = None,
    match_geometry_type: str | None = None,
) -> bool:
    """True when type policy allows a pair but label/content checks forbid linking."""
    return not cache_hit_sane_for_substrate(
        substrate_location_type=substrate_location_type,
        location_text=location_text,
        components=components,
        match_label=match_label,
        match_formatted_address=match_formatted_address,
        match_location_type=match_location_type,
        match_geometry_type=match_geometry_type,
    )
