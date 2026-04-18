"""Pure scoring for substrate ↔ canonical fuzzy match (v1, no LLM)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Literal

# Tunable thresholds (single place for policy + tests).
AUTOLINK_MIN_SCORE: float = 0.82
RECALL_MIN_SCORE: float = 0.28

_STRING_WEIGHT_WITH_SPATIAL: float = 0.86
_SPATIAL_WEIGHT: float = 0.14

# Spatial agreement: ~0 beyond this distance (meters).
_SPATIAL_HALF_LIFE_M: float = 2500.0


@dataclass(frozen=True)
class SubstrateMatchInput:
    """Normalized substrate naming + optional GeoJSON-ish geometry."""

    name: str
    normalized_name: str
    geometry_json: dict[str, Any] | None = None


@dataclass(frozen=True)
class CanonicalMatchFeatures:
    """Per-candidate fields used by the scorer."""

    canonical_id: int
    label: str
    normalized_aliases: tuple[str, ...]
    geometry_json: dict[str, Any] | None = None
    """Optional trigram / recall signal from the DB layer (Postgres ``similarity``)."""

    retrieval_string_hint: float | None = None


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return float(SequenceMatcher(None, a, b).ratio())


def _point_from_geometry_json(g: dict[str, Any] | None) -> tuple[float, float] | None:
    if g is None:
        return None
    t = g.get("type")
    if t != "Point":
        return None
    coords = g.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        return None
    try:
        lon = float(coords[0])
        lat = float(coords[1])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lat) or not math.isfinite(lon):
        return None
    return (lat, lon)


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in meters (WGS84 sphere)."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(min(1.0, math.sqrt(h)))
    return 6371000.0 * c


def spatial_score_from_distance_m(distance_m: float | None) -> float | None:
    """Map distance to [0, 1]; ``None`` if geometry is missing."""
    if distance_m is None:
        return None
    if distance_m <= 0.0:
        return 1.0
    # Exponential decay: strong when close, ~0 when far.
    return float(math.exp(-distance_m / _SPATIAL_HALF_LIFE_M))


def string_score_for_candidate(
    substrate: SubstrateMatchInput,
    candidate: CanonicalMatchFeatures,
) -> float:
    norm = substrate.normalized_name.strip().lower()
    parts: list[float] = []
    if candidate.retrieval_string_hint is not None:
        parts.append(max(0.0, min(1.0, float(candidate.retrieval_string_hint))))
    parts.append(_ratio(norm, candidate.label.strip().lower()))
    for a in candidate.normalized_aliases:
        parts.append(_ratio(norm, a.strip().lower()))
        if norm == a.strip().lower():
            parts.append(1.0)
    return max(parts) if parts else 0.0


def combined_score(
    substrate: SubstrateMatchInput,
    candidate: CanonicalMatchFeatures,
) -> float:
    """Blend string + optional spatial when both sides have a Point."""
    s_str = string_score_for_candidate(substrate, candidate)
    p_sub = _point_from_geometry_json(substrate.geometry_json)
    p_can = _point_from_geometry_json(candidate.geometry_json)
    if p_sub is None or p_can is None:
        return s_str
    d_m = haversine_m(p_sub, p_can)
    s_sp = spatial_score_from_distance_m(d_m)
    if s_sp is None:
        return s_str
    return _STRING_WEIGHT_WITH_SPATIAL * s_str + _SPATIAL_WEIGHT * s_sp


def classify_recall_score(score: float) -> Literal["autolink", "ambiguous", "below_recall"]:
    if score >= AUTOLINK_MIN_SCORE:
        return "autolink"
    if score >= RECALL_MIN_SCORE:
        return "ambiguous"
    return "below_recall"
