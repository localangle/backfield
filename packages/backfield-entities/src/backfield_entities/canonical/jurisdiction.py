"""Jurisdiction + geometry helpers for canonical autolink gates (Stylebook-only deps)."""

from __future__ import annotations

import math
import os
import re
from typing import Any

from backfield_db import SubstrateLocation

# US states + DC + Canadian provinces/territories (same set as geocode emit heuristics).
SUBNATIONAL_2: frozenset[str] = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "AB",
        "BC",
        "MB",
        "NB",
        "NL",
        "NS",
        "NT",
        "NU",
        "ON",
        "PE",
        "QC",
        "SK",
        "YT",
    }
)

_CA_SUBDIVISIONS: frozenset[str] = frozenset(
    {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}
)
_US_SUBDIVISIONS: frozenset[str] = SUBNATIONAL_2 - _CA_SUBDIVISIONS

_SUBDIVISION_TAIL_RE = re.compile(r"^([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?$")


def strict_canonical_gates_enabled() -> bool:
    v = (os.environ.get("BACKFIELD_STRICT_CANONICAL_GATES") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def place_extract_components_from_entry(
    location: SubstrateLocation,
    entry: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return PlaceExtract ``components`` dict from the ingest entry or persisted source details."""
    if isinstance(entry, dict):
        raw = entry.get("components")
        if isinstance(raw, dict):
            return raw
    sd = location.source_details_json if isinstance(location.source_details_json, dict) else None
    if sd:
        raw2 = sd.get("place_extract_components")
        if isinstance(raw2, dict):
            return raw2
    return {}


def jurisdiction_from_components(
    comps: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    """Return ``(country_code, subdivision_code, city_name)`` uppercased for codes."""
    country: str | None = None
    subdivision: str | None = None
    city_name: str | None = None

    c_country = comps.get("country")
    if isinstance(c_country, dict):
        abbr = c_country.get("abbr")
        if isinstance(abbr, str) and len(abbr.strip()) >= 2:
            country = abbr.strip().upper()[:2]

    c_state = comps.get("state")
    if isinstance(c_state, dict):
        sabbr = c_state.get("abbr")
        if isinstance(sabbr, str) and len(sabbr.strip()) >= 2:
            subdivision = sabbr.strip().upper()[:2]

    c_city = comps.get("city")
    if isinstance(c_city, str) and c_city.strip():
        city_name = c_city.strip()
    return country, subdivision, city_name


def stylebook_jurisdiction_fields_from_components(
    comps: dict[str, Any],
) -> dict[str, str | None]:
    """Keyword args for :class:`StylebookLocationCanonical` jurisdiction columns."""
    country, subdivision, city = jurisdiction_from_components(comps)
    return {
        "country_code": country,
        "subdivision_code": subdivision,
        "city_name": city,
    }


def _country_for_subdivision_code(code: str) -> str | None:
    if code in _US_SUBDIVISIONS:
        return "US"
    if code in _CA_SUBDIVISIONS:
        return "CA"
    return None


def _subdivision_from_address_tail(tail: str) -> str | None:
    """Parse ``AR`` or ``AR 71923`` (and similar) from the last comma segment."""
    cand = tail.upper().replace(".", "").strip()
    if len(cand) == 2 and cand in SUBNATIONAL_2:
        return cand
    m = _SUBDIVISION_TAIL_RE.fullmatch(cand)
    if m and m.group(1) in SUBNATIONAL_2:
        return m.group(1)
    return None


def parse_jurisdiction_from_formatted_address(
    formatted_address: str | None,
) -> tuple[str | None, str | None]:
    """Best-effort ``(country_code, subdivision_code)`` from a geocoder-style address string."""
    if not formatted_address or not str(formatted_address).strip():
        return None, None
    parts = [p.strip() for p in str(formatted_address).split(",") if p.strip()]
    if not parts:
        return None, None
    country: str | None = None
    state: str | None = None
    work = list(parts)
    last = work[-1].upper().replace(".", "")
    if last in ("US", "USA", "UNITED STATES"):
        country = "US"
        work = work[:-1]
    if work:
        sub = _subdivision_from_address_tail(work[-1])
        if sub is not None:
            state = sub
            if country is None:
                country = _country_for_subdivision_code(sub)
    return country, state


def geocode_components_vs_formatted_address_mismatch(
    *,
    formatted_address: str | None,
    comps: dict[str, Any],
) -> str | None:
    """Return gate code ``geocode_country_mismatch`` / ``geocode_state_mismatch`` or ``None``."""
    c_country, c_state = jurisdiction_from_components(comps)[:2]
    g_country, g_state = parse_jurisdiction_from_formatted_address(formatted_address)
    if c_country and g_country and c_country != g_country:
        return "geocode_country_mismatch"
    if c_state and g_state and c_state != g_state:
        return "geocode_state_mismatch"
    return None


def _bbox_diagonal_km(lon_min: float, lat_min: float, lon_max: float, lat_max: float) -> float:
    """Great-circle length of the diagonal of the lon/lat bounding box (km)."""
    mid_lat = (lat_min + lat_max) / 2.0
    dx = haversine_km(lon_min, mid_lat, lon_max, mid_lat)
    dy = haversine_km(lon_min, lat_min, lon_min, lat_max)
    return math.hypot(dx, dy)


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _iter_lon_lat_pairs(obj: Any) -> Any:
    if isinstance(obj, (list, tuple)):
        if (
            len(obj) >= 2
            and isinstance(obj[0], (int, float))
            and isinstance(obj[1], (int, float))
        ):
            yield float(obj[0]), float(obj[1])
        else:
            for x in obj:
                yield from _iter_lon_lat_pairs(x)


def geojson_bbox_centroid(geometry_json: dict[str, Any] | None) -> tuple[float, float] | None:
    """Centroid of the lon/lat axis-aligned bounding box of GeoJSON coordinates."""
    if not isinstance(geometry_json, dict):
        return None
    pairs = list(_iter_lon_lat_pairs(geometry_json.get("coordinates")))
    if not pairs:
        return None
    lons = [p[0] for p in pairs]
    lats = [p[1] for p in pairs]
    return (min(lons) + max(lons)) / 2.0, (min(lats) + max(lats)) / 2.0


def geojson_bbox_diagonal_km(geometry_json: dict[str, Any] | None) -> float | None:
    """Diagonal length (km) of bbox; ``None`` if coordinates missing."""
    if not isinstance(geometry_json, dict):
        return None
    pairs = list(_iter_lon_lat_pairs(geometry_json.get("coordinates")))
    if not pairs:
        return None
    lons = [p[0] for p in pairs]
    lats = [p[1] for p in pairs]
    return _bbox_diagonal_km(min(lons), min(lats), max(lons), max(lats))


def container_admin_query_from_components(comps: dict[str, Any]) -> str | None:
    """``City, ST, CC`` query string for cache / container-distance reference."""
    country, subdivision, city = jurisdiction_from_components(comps)
    if not city or not subdivision:
        return None
    cc = country if country else "US"
    if isinstance(cc, str) and len(cc) == 2:
        return f"{city}, {subdivision}, {cc}"
    return None


_ALLOWED_DISTRICT_KINDS: frozenset[str] = frozenset(
    {
        "ward",
        "us_house",
        "state_senate",
        "state_house",
        "city_council",
        "precinct",
        "other",
    }
)


def normalize_district_number_token(raw: str) -> str:
    """Normalize district number for identity keys (alphanumeric + hyphens, lenient)."""
    s = str(raw or "").strip().upper()
    out: list[str] = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in ("-", "/", " "):
            if out and out[-1] != "-":
                out.append("-")
    while out and out[-1] == "-":
        out.pop()
    return "".join(out)


def district_identity_from_components(
    comps: dict[str, Any],
) -> tuple[str, str, str, str] | None:
    """Return ``(kind, number_normalized, subdivision_code, country_code)`` or ``None``.

    Requires a non-empty normalized district number and a 2-letter subdivision (state) code.
    """
    if not isinstance(comps, dict):
        return None
    raw = comps.get("district")
    dist = raw if isinstance(raw, dict) else {}
    kind = str(dist.get("kind") or "").strip().lower()
    if kind and kind not in _ALLOWED_DISTRICT_KINDS:
        kind = "other"
    if not kind:
        kind = "other"
    num_raw = str(dist.get("number") or "").strip()
    if not num_raw:
        return None
    num_norm = normalize_district_number_token(num_raw)
    if not num_norm:
        return None
    country, subdivision, _city = jurisdiction_from_components(comps)
    if not subdivision or len(subdivision) != 2:
        return None
    cc = (country or "US").strip().upper()[:2]
    if len(cc) != 2:
        cc = "US"
    return (kind, num_norm, subdivision, cc)


def district_identity_key(identity: tuple[str, str, str, str] | None) -> str | None:
    """Stable key: ``{country}-{KIND}-{state}-{number}`` (e.g. ``US-US-HOUSE-MN-08``)."""
    if identity is None:
        return None
    kind, num, state, country = identity
    kind_part = kind.upper().replace("_", "-")
    return f"{country}-{kind_part}-{state}-{num}"


def stylebook_district_fields_from_components(comps: dict[str, Any]) -> dict[str, str | None]:
    """Keyword args for :class:`StylebookLocationCanonical` district columns from PlaceExtract."""
    raw = comps.get("district") if isinstance(comps.get("district"), dict) else {}
    kind = str(raw.get("kind") or "").strip() or None
    num = str(raw.get("number") or "").strip() or None
    return {
        "district_kind": kind,
        "district_number": num,
        "district_key": district_identity_key(district_identity_from_components(comps)),
    }


# Deterministic district-kind signal from display text. PlaceExtract sometimes misfiles a
# district phrase (e.g. "13th subcircuit") in the city component, leaving no structured
# district identity, so name/label keywords are the only cheap way to tell a judicial
# subcircuit from a congressional district from a ward. Single-word keywords match tokens;
# multi-word keywords match token bigrams.
_DISTRICT_KIND_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("judicial", ("subcircuit", "judicial")),
    ("us_house", ("congressional",)),
    ("ward", ("ward",)),
    ("state_senate", ("state senate",)),
    ("state_house", ("state house",)),
)

_KEYWORD_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def district_kind_keyword_from_text(text: str | None) -> str | None:
    """District kind implied by the head (first comma segment) of a display name, or ``None``."""
    head = str(text or "").split(",")[0].strip().lower()
    if not head:
        return None
    tokens = [t for t in _KEYWORD_TOKEN_RE.split(head) if t]
    if not tokens:
        return None
    token_set = set(tokens)
    bigrams = {f"{a} {b}" for a, b in zip(tokens, tokens[1:])}
    for kind, keywords in _DISTRICT_KIND_KEYWORDS:
        for kw in keywords:
            if (" " in kw and kw in bigrams) or (" " not in kw and kw in token_set):
                return kind
    return None


def district_kind_keywords_conflict(
    substrate_texts: tuple[str | None, ...],
    canonical_texts: tuple[str | None, ...],
) -> bool:
    """True when both sides carry district-kind keywords and they do not agree.

    A substrate whose own texts disagree (e.g. name says "Congressional District 13" while
    the geocoded address says "13th subcircuit") conflicts with any single-kind canonical:
    the identity is uncertain, so the pair should not link without human review.
    """
    sub_kinds = {
        kind
        for t in substrate_texts
        if (kind := district_kind_keyword_from_text(t)) is not None
    }
    canon_kinds = {
        kind
        for t in canonical_texts
        if (kind := district_kind_keyword_from_text(t)) is not None
    }
    if not sub_kinds or not canon_kinds:
        return False
    return len(sub_kinds | canon_kinds) >= 2


def geojson_point_lon_lat(geometry_json: dict[str, Any] | None) -> tuple[float, float] | None:
    """Lon/lat for a GeoJSON Point, or ``None``."""
    if not isinstance(geometry_json, dict):
        return None
    if str(geometry_json.get("type") or "").lower() != "point":
        return None
    coords = geometry_json.get("coordinates")
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        return None
    try:
        lon = float(coords[0])
        lat = float(coords[1])
    except (TypeError, ValueError):
        return None
    return lon, lat


def geojson_lon_lat_bbox(
    geometry_json: dict[str, Any] | None,
) -> tuple[float, float, float, float] | None:
    """Axis-aligned bbox ``(min_lon, min_lat, max_lon, max_lat)`` from GeoJSON coordinates."""
    if not isinstance(geometry_json, dict):
        return None
    pairs = list(_iter_lon_lat_pairs(geometry_json.get("coordinates")))
    if not pairs:
        return None
    lons = [p[0] for p in pairs]
    lats = [p[1] for p in pairs]
    return (min(lons), min(lats), max(lons), max(lats))


def point_in_geojson_bbox(
    lon: float,
    lat: float,
    geometry_json: dict[str, Any] | None,
) -> bool:
    """True when ``(lon, lat)`` lies inside the lon/lat axis-aligned bbox of ``geometry_json``."""
    bbox = geojson_lon_lat_bbox(geometry_json)
    if bbox is None:
        return False
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat