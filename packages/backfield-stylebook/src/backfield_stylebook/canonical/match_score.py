"""Pure scoring for substrate ↔ canonical fuzzy match (v1, no LLM)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Literal

from number_parser import parse_number, parse_ordinal

# Collapse punctuation so "West Garfield Park, Chicago, IL" and "West Garfield Park — Chicago IL"
# compare as the same place name for scoring.
_LOOSE_TOKEN_RE = re.compile(r"[^a-z0-9]+")
_ORDINAL_SUFFIX_RE = re.compile(r"\b(\d+)(st|nd|rd|th)\b", re.IGNORECASE)

# ``number_parser.parse`` rewrites bare cardinals (``Six Flags`` → ``6 Flags``); we only use
# :func:`parse_ordinal` / :func:`parse_number` on token windows with a cardinal guard.
_NUMBER_PARSER_LANG = "en"
# Longest English ordinals in practice (e.g. ``one hundred twenty first``).
_MAX_WORD_ORDINAL_WINDOW = 12
_CONCAT_COMPOUND_ORDINAL_RE = re.compile(
    r"^(twenty|thirty)(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth)$"
)


def _expand_concat_compound_ordinal_token(token: str) -> list[str]:
    """Split rare glued forms (``twentyfirst``) so :func:`parse_ordinal` can read them."""
    m = _CONCAT_COMPOUND_ORDINAL_RE.match(token)
    if not m:
        return [token]
    return [m.group(1), m.group(2)]


def _normalize_word_ordinal_tokens(tokens: list[str]) -> list[str]:
    """Replace spelled ordinals with digit tokens using ``number-parser``.

    Skips pure cardinal phrases (``twenty one``, ``six``) so we do not mimic
    :func:`number_parser.parse` on full strings.
    """
    expanded: list[str] = []
    for t in tokens:
        expanded.extend(_expand_concat_compound_ordinal_token(t))
    tpl = expanded
    out: list[str] = []
    i = 0
    lang = _NUMBER_PARSER_LANG
    while i < len(tpl):
        max_w = min(_MAX_WORD_ORDINAL_WINDOW, len(tpl) - i)
        replaced = False
        for w in range(max_w, 1, -1):
            phrase = " ".join(tpl[i : i + w])
            ord_val = parse_ordinal(phrase, language=lang)
            if ord_val is None:
                continue
            num_val = parse_number(phrase, language=lang)
            if num_val is not None and num_val == ord_val:
                continue
            out.append(str(ord_val))
            i += w
            replaced = True
            break
        if replaced:
            continue
        t = tpl[i]
        ord_val = parse_ordinal(t, language=lang)
        num_val = parse_number(t, language=lang)
        if ord_val is not None and not (num_val is not None and num_val == ord_val):
            out.append(str(ord_val))
        else:
            out.append(t)
        i += 1
    return out


# Map common US state tokens so ``IL`` vs ``Illinois`` does not break token-coverage checks.
_US_STATE_ABBR_FULL: dict[str, str] = {
    "al": "alabama",
    "ak": "alaska",
    "az": "arizona",
    "ar": "arkansas",
    "ca": "california",
    "co": "colorado",
    "ct": "connecticut",
    "de": "delaware",
    "dc": "districtofcolumbia",
    "fl": "florida",
    "ga": "georgia",
    "hi": "hawaii",
    "id": "idaho",
    "il": "illinois",
    "in": "indiana",
    "ia": "iowa",
    "ks": "kansas",
    "ky": "kentucky",
    "la": "louisiana",
    "me": "maine",
    "md": "maryland",
    "ma": "massachusetts",
    "mi": "michigan",
    "mn": "minnesota",
    "ms": "mississippi",
    "mo": "missouri",
    "mt": "montana",
    "ne": "nebraska",
    "nv": "nevada",
    "nh": "newhampshire",
    "nj": "newjersey",
    "nm": "newmexico",
    "ny": "newyork",
    "nc": "northcarolina",
    "nd": "northdakota",
    "oh": "ohio",
    "ok": "oklahoma",
    "or": "oregon",
    "pa": "pennsylvania",
    "ri": "rhodeisland",
    "sc": "southcarolina",
    "sd": "southdakota",
    "tn": "tennessee",
    "tx": "texas",
    "ut": "utah",
    "vt": "vermont",
    "va": "virginia",
    "wa": "washington",
    "wv": "westvirginia",
    "wi": "wisconsin",
    "wy": "wyoming",
}


def _expand_us_state_tokens(toks: set[str]) -> set[str]:
    """Add paired state name / abbreviation tokens so coverage checks stay stable."""
    out = set(toks)
    for t in list(toks):
        low = t.lower()
        full = _US_STATE_ABBR_FULL.get(low)
        if full:
            out.add(full)
    for t in list(toks):
        low = t.lower()
        for abbr, full in _US_STATE_ABBR_FULL.items():
            if low == full:
                out.add(abbr)
    return out

# Tunable thresholds (single place for policy + tests).
AUTOLINK_MIN_SCORE: float = 0.9
RECALL_MIN_SCORE: float = 0.28

_STRING_WEIGHT_WITH_SPATIAL: float = 0.86
_SPATIAL_WEIGHT: float = 0.14

# Spatial agreement: ~0 beyond this distance (meters).
_SPATIAL_HALF_LIFE_M: float = 2500.0


@dataclass(frozen=True)
class SubstrateMatchInput:
    """Substrate naming surfaces + optional GeoJSON-ish geometry.

    ``formatted_address`` is optional geocoder text; it often carries extra tokens
    (``West Side``, ``USA``) while the editorial canonical ``label`` stays shorter.
    """

    name: str
    normalized_name: str
    geometry_json: dict[str, Any] | None = None
    formatted_address: str | None = None


@dataclass(frozen=True)
class CanonicalMatchFeatures:
    """Per-candidate fields used by the scorer."""

    canonical_id: str
    label: str
    normalized_aliases: tuple[str, ...]
    geometry_json: dict[str, Any] | None = None
    """Optional trigram / recall signal from the DB layer (Postgres ``similarity``)."""

    retrieval_string_hint: float | None = None


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return float(SequenceMatcher(None, a, b).ratio())


def _loose_key(value: str) -> str:
    """Lowercase alnum tokens joined by single spaces (commas/dashes ignored)."""
    raw = value.strip().lower()
    # Collapse punctuation to spaces so hyphenated ordinals (``twenty-first``) become
    # separate tokens (``twenty``, ``first``) for :func:`_normalize_word_ordinal_tokens`.
    norm = " ".join(_LOOSE_TOKEN_RE.sub(" ", raw).split())
    if norm:
        toks = [t for t in norm.split() if t]
        norm = " ".join(_normalize_word_ordinal_tokens(toks))
    norm = _ORDINAL_SUFFIX_RE.sub(r"\1", norm)
    t = _LOOSE_TOKEN_RE.sub(" ", norm).strip()
    return " ".join(t.split())


def _substrate_surface_strings(substrate: SubstrateMatchInput) -> list[str]:
    """Distinct non-empty lowercased strings to compare against canonical naming.

    Includes ``formatted_address`` for weaker ratio-based comparisons only.
    Use :func:`_substrate_name_surface_strings` for identity heuristics.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in (
        substrate.normalized_name,
        substrate.name,
        substrate.formatted_address or "",
    ):
        s = raw.strip().lower()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _substrate_name_surface_strings(substrate: SubstrateMatchInput) -> list[str]:
    """Like :func:`_substrate_surface_strings` but excludes ``formatted_address``.

    Used for identity heuristics (token coverage, substring identity) so that a
    geocoder-supplied ``formatted_address`` containing a trailing city/state tail
    (e.g. ``…, Chicago, IL, USA``) cannot inflate the score of a broad city canonical
    to 1.0 for an unrelated specific place.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in (substrate.normalized_name, substrate.name):
        s = raw.strip().lower()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _meaningful_token_set(loose: str) -> set[str]:
    return {t for t in loose.split() if len(t) >= 2}


def _token_set_coverage_score(canonical_loose: str, substrate_surfaces: list[str]) -> float | None:
    """1.0 when every meaningful token from the canonical label appears on some substrate surface.

    Handles geocoder ``formatted_address`` strings that extend the place name with
    neighborhood or country tokens without changing the core location identity.
    """
    raw_ct = _meaningful_token_set(canonical_loose)
    # Guard on the raw (pre-expansion) count so that a two-token canonical like
    # "Chicago, IL" cannot reach 3 tokens via US-state abbreviation expansion and
    # then spuriously match every Chicago-area location name.
    if len(raw_ct) < 3:
        return None
    ct = _expand_us_state_tokens(raw_ct)
    union: set[str] = set()
    for surf in substrate_surfaces:
        union |= _expand_us_state_tokens(_meaningful_token_set(_loose_key(surf)))
    if not union:
        return None
    if ct <= union:
        return 1.0
    return None


def _loose_substring_identity_score(loose_label: str, surfaces: list[str]) -> float | None:
    """1.0 for near-identical place name matches (not containment).

    Two cases:
    - Substrate is a substring of (or equal to) canonical → identity (canonical is broader
      or same; keep for alias / abbreviation matching).
    - Canonical is a substring of substrate AND canonical is at least 55 % of the substrate
      blob length → identity.  The length guard blocks a short canonical like "Chicago, IL"
      from scoring 1.0 just because ", Chicago, IL" appears as a trailing suffix in every
      Chicago-area location name (containment, not identity).
    """
    if len(loose_label) < 10:
        return None
    blob = " ".join(_loose_key(s) for s in surfaces if s.strip())
    if not blob:
        return None
    if loose_label in blob and len(loose_label) >= 0.55 * len(blob):
        return 1.0
    if len(blob) >= 10 and blob in loose_label:
        return 1.0
    return None


def _string_score_surface_vs_candidate(norm: str, candidate: CanonicalMatchFeatures) -> float:
    """Compare one substrate surface string to label + aliases (no trigram hint)."""
    norm = norm.strip().lower()
    if not norm:
        return 0.0
    loose_n = _loose_key(norm)
    parts: list[float] = []
    label_lower = candidate.label.strip().lower()
    loose_label = _loose_key(candidate.label)
    if norm == label_lower:
        parts.append(1.0)
    if loose_n and loose_n == loose_label:
        parts.append(1.0)
    parts.append(_ratio(norm, label_lower))
    if loose_n:
        parts.append(_ratio(loose_n, loose_label))
    for a in candidate.normalized_aliases:
        a_st = a.strip().lower()
        parts.append(_ratio(norm, a_st))
        if norm == a_st:
            parts.append(1.0)
        loose_a = _loose_key(a)
        if loose_n and loose_n == loose_a:
            parts.append(1.0)
        if loose_n:
            parts.append(_ratio(loose_n, loose_a))
    return max(parts) if parts else 0.0


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
    # All surfaces (including formatted_address) used for weaker ratio-based comparisons.
    surfaces = _substrate_surface_strings(substrate)
    # Name-only surfaces (no formatted_address) used for identity→1.0 shortcuts so that a
    # geocoder city/state tail cannot inflate a broad canonical's score to 1.0 for a
    # specific sub-place whose name merely ends with ``…, Chicago, IL``.
    name_surfaces = _substrate_name_surface_strings(substrate)
    parts: list[float] = []
    if candidate.retrieval_string_hint is not None:
        parts.append(max(0.0, min(1.0, float(candidate.retrieval_string_hint))))
    for surf in surfaces:
        parts.append(_string_score_surface_vs_candidate(surf, candidate))

    loose_label = _loose_key(candidate.label)
    cov = _token_set_coverage_score(loose_label, name_surfaces)
    if cov is not None:
        parts.append(cov)
    subseq = _loose_substring_identity_score(loose_label, name_surfaces)
    if subseq is not None:
        parts.append(subseq)
    for a in candidate.normalized_aliases:
        acov = _token_set_coverage_score(_loose_key(a), name_surfaces)
        if acov is not None:
            parts.append(acov)

    return max(parts) if parts else 0.0


def combined_score(
    substrate: SubstrateMatchInput,
    candidate: CanonicalMatchFeatures,
) -> float:
    """Blend string + optional spatial when both sides have a Point.

    Geography never reduces the score below string-only: mismatched or missing pins
    should not block a strong name match (spatial is an optional boost).
    """
    s_str = string_score_for_candidate(substrate, candidate)
    p_sub = _point_from_geometry_json(substrate.geometry_json)
    p_can = _point_from_geometry_json(candidate.geometry_json)
    if p_sub is None or p_can is None:
        return s_str
    d_m = haversine_m(p_sub, p_can)
    s_sp = spatial_score_from_distance_m(d_m)
    if s_sp is None:
        return s_str
    blended = _STRING_WEIGHT_WITH_SPATIAL * s_str + _SPATIAL_WEIGHT * s_sp
    return max(s_str, blended)


def policy_match_score(
    substrate: SubstrateMatchInput,
    candidate: CanonicalMatchFeatures,
    *,
    substrate_location_type: str | None,
) -> float:
    """Score used for autolink / ambiguous thresholds.

    For **non-address** places (neighborhood, city, etc.), only **string** similarity
    is used so proximity is not part of the decision—geography is reserved mainly for
    **address → place** style matches where names often disagree but pins may agree.
    """
    s_str = string_score_for_candidate(substrate, candidate)
    if (substrate_location_type or "").strip().lower() == "address":
        return combined_score(substrate, candidate)
    return s_str


def classify_recall_score(score: float) -> Literal["autolink", "ambiguous", "below_recall"]:
    if score >= AUTOLINK_MIN_SCORE:
        return "autolink"
    if score >= RECALL_MIN_SCORE:
        return "ambiguous"
    return "below_recall"
