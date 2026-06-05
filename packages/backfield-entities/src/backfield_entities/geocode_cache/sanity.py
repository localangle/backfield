"""Sanity gates for geocode cache hits (tier 1 canonical, tier 2 substrate cache, adjudication)."""

from __future__ import annotations

import re
from typing import Any

from backfield_entities.canonical.link_matrix import (
    autolink_container_to_fine_denied,
    link_pair_allowed,
)
from backfield_entities.geocode_cache.fingerprint import normalize_substrate_cache_query

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
_POI_LIKE_CANONICAL_TYPES: frozenset[str] = frozenset({"place", "point", "neighborhood"})

_HOUSE_NUMBER_RE = re.compile(r"\d")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


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


def _place_name_token(components: dict[str, Any] | None) -> str:
    c = components if isinstance(components, dict) else {}
    place = c.get("place")
    if isinstance(place, dict):
        return str(place.get("name") or "").strip().lower()
    return str(place or "").strip().lower()


def _label_contains_token(label: str, token: str) -> bool:
    t = (token or "").strip().lower()
    if len(t) < 2:
        return False
    return t in (label or "").strip().lower()


def _compare_key(text: str) -> str:
    """Loose key for substring checks (drops punctuation differences in street lines)."""
    return _NON_ALNUM_RE.sub(" ", (text or "").strip().lower()).strip()


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

    if substrate_lt == "address":
        addr_line = address_line_from_components(components, location_text)
        if not address_requests_street_resolution(addr_line):
            return True
        poi = _place_name_token(components)
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
        return True

    if substrate_lt in ("place", "point"):
        token = _place_name_token(components)
        if len(token) >= 2 and canon_lt in (
            "city",
            "town",
            "village",
            "place",
            "point",
            "neighborhood",
        ):
            if not _label_contains_token(label_blob, token):
                return False
        return True

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
