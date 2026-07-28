"""Deduplicate repeated geocodes for the same place within one article."""

from __future__ import annotations

import copy
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_POINT_TYPES = frozenset({"address", "place", "point"})
_AREA_BUCKETS = ("states", "counties", "cities", "neighborhoods", "regions", "other")
_EARTH_RADIUS_METERS = 6_371_000.0
_SAME_NAMED_PLACE_MAX_DISTANCE_METERS = 300.0


@dataclass
class _RetainedPlace:
    bucket: str
    entry: dict[str, Any]


def _fold_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = text.encode("ascii", "ignore").decode("ascii").lower()
    return _NON_ALNUM_RE.sub(" ", ascii_text).strip()


def _display_name(entry: dict[str, Any]) -> str:
    location = entry.get("location")
    if isinstance(location, str):
        return location.strip()
    if isinstance(location, dict):
        full = location.get("full")
        if isinstance(full, str):
            return full.strip()
    return ""


def _type_family(entry: dict[str, Any]) -> str:
    location_type = _fold_text(entry.get("type"))
    if location_type == "town":
        return "city"
    return location_type


def _component_text(entry: dict[str, Any], key: str) -> str:
    components = entry.get("components")
    if not isinstance(components, dict):
        return ""
    value = components.get(key)
    if isinstance(value, dict):
        value = value.get("abbr") or value.get("name") or value.get("label")
    return _fold_text(value)


def _jurisdictions_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for key in ("city", "state", "country"):
        left_value = _component_text(left, key)
        right_value = _component_text(right, key)
        if left_value and right_value and left_value != right_value:
            return False
    return True


def _geocode_result(entry: dict[str, Any]) -> dict[str, Any]:
    geocode = entry.get("geocode")
    if not isinstance(geocode, dict):
        return {}
    result = geocode.get("result")
    return result if isinstance(result, dict) else {}


def _identity_tokens(entry: dict[str, Any]) -> frozenset[str]:
    result = _geocode_result(entry)
    tokens: set[str] = set()
    canonical_id = result.get("canonical_id")
    if canonical_id is not None and str(canonical_id).strip():
        tokens.add(f"canonical:{str(canonical_id).strip()}")
    result_id = result.get("id")
    if result_id is not None and str(result_id).strip():
        tokens.add(f"result:{str(result_id).strip()}")
    return frozenset(tokens)


def _point_coordinates(entry: dict[str, Any]) -> tuple[float, float] | None:
    geometry = _geocode_result(entry).get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 2:
        return None
    try:
        return float(coordinates[0]), float(coordinates[1])
    except (TypeError, ValueError):
        return None


def _distance_meters(
    left: tuple[float, float],
    right: tuple[float, float],
) -> float:
    left_lon, left_lat = left
    right_lon, right_lat = right
    lat1 = math.radians(left_lat)
    lat2 = math.radians(right_lat)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(right_lon - left_lon)
    haversine = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * _EARTH_RADIUS_METERS * math.asin(min(1.0, math.sqrt(haversine)))


def _same_place(left: _RetainedPlace, right: _RetainedPlace) -> bool:
    left_name = _fold_text(_display_name(left.entry))
    right_name = _fold_text(_display_name(right.entry))
    if not left_name or left_name != right_name:
        return False
    if _type_family(left.entry) != _type_family(right.entry):
        return False
    if not _jurisdictions_compatible(left.entry, right.entry):
        return False

    if _type_family(left.entry) not in _POINT_TYPES:
        return True

    shared_identity = _identity_tokens(left.entry) & _identity_tokens(right.entry)
    if shared_identity:
        return True

    left_coordinates = _point_coordinates(left.entry)
    right_coordinates = _point_coordinates(right.entry)
    if left_coordinates is not None and right_coordinates is not None:
        return (
            _distance_meters(left_coordinates, right_coordinates)
            <= _SAME_NAMED_PLACE_MAX_DISTANCE_METERS
        )

    # A resolved row and an otherwise identical review row represent one extraction.
    return (left.bucket == "needs_review") != (right.bucket == "needs_review")


def _ordered_unique_strings(values: list[object]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        clean = value.strip()
        key = _fold_text(clean)
        if not clean or not key or key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


def _mention_texts(entry: dict[str, Any]) -> list[str]:
    out: list[object] = []
    mentions = entry.get("mentions")
    if isinstance(mentions, list):
        for mention in mentions:
            if isinstance(mention, dict):
                out.append(mention.get("text"))
    out.append(entry.get("original_text"))
    return _ordered_unique_strings(out)


def _string_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _quality_score(place: _RetainedPlace) -> int:
    score = 0
    if place.bucket != "needs_review":
        score += 100
    if _point_coordinates(place.entry) is not None:
        score += 20
    if any(token.startswith("canonical:") for token in _identity_tokens(place.entry)):
        score += 10
    if _fold_text(place.entry.get("type")) == "place":
        score += 5
    return score


def _merge_entries(
    preferred: dict[str, Any],
    other: dict[str, Any],
    *,
    mention_order: tuple[dict[str, Any], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    merged = copy.deepcopy(preferred)
    evidence_sources = mention_order or (preferred, other)
    mention_texts = _ordered_unique_strings(
        [
            *_mention_texts(evidence_sources[0]),
            *_mention_texts(evidence_sources[1]),
        ]
    )
    if mention_texts:
        merged["mentions"] = [{"text": text} for text in mention_texts]
        merged["original_text"] = mention_texts[0]

    tags = _ordered_unique_strings(
        [
            *_string_list(preferred.get("nature_secondary_tags")),
            *_string_list(other.get("nature_secondary_tags")),
        ]
    )
    if tags:
        merged["nature_secondary_tags"] = tags
    return merged


def _merge_duplicate(retained: _RetainedPlace, duplicate: _RetainedPlace) -> None:
    if _quality_score(duplicate) > _quality_score(retained):
        retained.entry = _merge_entries(
            duplicate.entry,
            retained.entry,
            mention_order=(retained.entry, duplicate.entry),
        )
        retained.bucket = duplicate.bucket
    else:
        retained.entry = _merge_entries(retained.entry, duplicate.entry)


def _iter_places(places: dict[str, Any]) -> list[_RetainedPlace]:
    rows: list[_RetainedPlace] = []
    areas = places.get("areas")
    if isinstance(areas, dict):
        for bucket in _AREA_BUCKETS:
            entries = areas.get(bucket)
            if isinstance(entries, list):
                rows.extend(
                    _RetainedPlace(bucket=bucket, entry=copy.deepcopy(entry))
                    for entry in entries
                    if isinstance(entry, dict)
                )
    for bucket in ("points", "needs_review"):
        entries = places.get(bucket)
        if isinstance(entries, list):
            rows.extend(
                _RetainedPlace(bucket=bucket, entry=copy.deepcopy(entry))
                for entry in entries
                if isinstance(entry, dict)
            )
    return rows


def deduplicate_consolidated_places(places: dict[str, Any]) -> dict[str, Any]:
    """Return one consolidated row for each confidently identical article place.

    Exact normalized names and compatible extraction types are required. Fine-grained
    places require a shared resolver identity, nearby point geometry, or a resolved/review
    pair. This deliberately avoids treating a shared address, provider identity, or H3 cell
    as identity across address, place, and point extractions.
    """
    retained: list[_RetainedPlace] = []
    for candidate in _iter_places(places):
        match = next(
            (existing for existing in retained if _same_place(existing, candidate)),
            None,
        )
        if match is None:
            retained.append(candidate)
        else:
            _merge_duplicate(match, candidate)

    deduplicated = {
        "areas": {bucket: [] for bucket in _AREA_BUCKETS},
        "points": [],
        "needs_review": [],
    }
    for place in retained:
        if place.bucket in _AREA_BUCKETS:
            deduplicated["areas"][place.bucket].append(place.entry)
        else:
            deduplicated[place.bucket].append(place.entry)
    return deduplicated
