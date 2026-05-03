"""Jurisdiction + geometry helpers for canonical autolink gates (Stylebook-only deps)."""

from __future__ import annotations

import math
import os
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
        cand = work[-1].upper().replace(".", "")
        if len(cand) == 2 and cand in SUBNATIONAL_2:
            state = cand
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