"""Precision-first POI evidence checks for external Pelias place geocoding.

Deliberately separate from ``backfield_entities.ingest.geocode_cache.sanity`` so
Stylebook/cache linking keeps its stricter house-number-in-label gate.
"""

from __future__ import annotations

import re
from typing import Any

from agate_utils.geocoding.geocoding_types import GeocodingResult
from backfield_entities.canonical.jurisdiction import jurisdiction_from_components
from backfield_entities.ingest.geocode_cache.sanity import named_location_heads_compatible

_HOUSE_NUMBER_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])(\d+[A-Za-z]?)(?![A-Za-z0-9])")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

_PELIAS_GEOCODER_PREFIXES: frozenset[str] = frozenset(
    {
        "pelias",
        "pelias_search",
        "pelias_structured",
    }
)


def is_pelias_geocoder(geocoder: str | None) -> bool:
    """True when the result came from a Pelias / Geocode.Earth path."""
    name = (geocoder or "").strip().lower()
    if not name:
        return False
    if name in _PELIAS_GEOCODER_PREFIXES:
        return True
    return name.startswith("pelias")


def _compare_key(text: str) -> str:
    return _NON_ALNUM_RE.sub(" ", (text or "").strip().lower()).strip()


def _confidence(result: GeocodingResult | None) -> dict[str, Any]:
    if result is None or result.result is None:
        return {}
    raw = getattr(result.result, "confidence", None)
    return raw if isinstance(raw, dict) else {}


def place_name_from_components(components: dict[str, Any] | None) -> str:
    """Extracted venue / POI name from PlaceExtract components."""
    comps = components if isinstance(components, dict) else {}
    place = comps.get("place")
    if isinstance(place, dict):
        name = str(place.get("name") or "").strip()
        if name:
            return name
    if isinstance(place, str) and place.strip():
        return place.strip()
    return ""


def street_address_from_components(components: dict[str, Any] | None) -> str:
    comps = components if isinstance(components, dict) else {}
    return str(comps.get("address") or "").strip()


def components_from_place_fields(
    *,
    name: str,
    street_address: str | None,
    city: str | None,
    state_abbr: str | None,
    country: str | None,
) -> dict[str, Any]:
    """Build a components-shaped dict from a Place model for evidence checks."""
    comps: dict[str, Any] = {
        "place": {"name": str(name or "").strip()},
    }
    if street_address and str(street_address).strip():
        comps["address"] = str(street_address).strip()
    if city and str(city).strip():
        comps["city"] = str(city).strip()
    if state_abbr and str(state_abbr).strip():
        comps["state"] = {"abbr": str(state_abbr).strip().upper()}
    if country and str(country).strip():
        cc = str(country).strip().upper()
        comps["country"] = {"abbr": cc[:2] if len(cc) >= 2 else cc}
    return comps


def _requested_house_number(components: dict[str, Any] | None) -> str | None:
    addr = street_address_from_components(components)
    if not addr:
        return None
    match = _HOUSE_NUMBER_TOKEN_RE.search(addr)
    if match is None:
        return None
    return match.group(1).lower()


def _candidate_house_numbers(result: GeocodingResult) -> set[str]:
    conf = _confidence(result)
    numbers: set[str] = set()
    structured = str(conf.get("pelias_housenumber") or "").strip()
    if structured:
        for token in _HOUSE_NUMBER_TOKEN_RE.findall(structured):
            numbers.add(token.lower())
    label = ""
    if result.result is not None:
        label = str(result.result.processed_str or "")
    for token in _HOUSE_NUMBER_TOKEN_RE.findall(label):
        numbers.add(token.lower())
    return numbers


def house_number_conflicts(
    components: dict[str, Any] | None,
    result: GeocodingResult,
) -> bool:
    """True when extract and provider both declare house numbers and they differ."""
    requested = _requested_house_number(components)
    if requested is None:
        return False
    candidate_numbers = _candidate_house_numbers(result)
    if not candidate_numbers:
        return False
    return requested not in candidate_numbers


def house_number_matches(
    components: dict[str, Any] | None,
    result: GeocodingResult,
) -> bool:
    """True when the extract's house number appears in Pelias structured or label evidence."""
    requested = _requested_house_number(components)
    if requested is None:
        return False
    return requested in _candidate_house_numbers(result)


def _city_tokens(value: str) -> set[str]:
    return {t for t in _compare_key(value).split() if len(t) >= 2}


def city_agrees(components: dict[str, Any] | None, result: GeocodingResult) -> bool:
    """Require explicit city agreement when the extract declares a city."""
    comps = components if isinstance(components, dict) else {}
    expected_city = str(comps.get("city") or "").strip()
    if not expected_city:
        return True
    conf = _confidence(result)
    candidates = [
        str(conf.get("pelias_locality") or "").strip(),
        str(conf.get("pelias_localadmin") or "").strip(),
        str(conf.get("pelias_borough") or "").strip(),
    ]
    expected_tokens = _city_tokens(expected_city)
    if not expected_tokens:
        return True
    for cand in candidates:
        if not cand:
            continue
        if named_location_heads_compatible(expected_city, cand):
            return True
        cand_tokens = _city_tokens(cand)
        if expected_tokens and expected_tokens <= cand_tokens:
            return True
        if expected_tokens and cand_tokens and expected_tokens == cand_tokens:
            return True
    return False


def state_agrees(components: dict[str, Any] | None, result: GeocodingResult) -> bool:
    """Require explicit state/region agreement when the extract declares a subdivision."""
    comps = components if isinstance(components, dict) else {}
    _country, expected_subdivision, _city = jurisdiction_from_components(comps)
    if not expected_subdivision:
        return True
    conf = _confidence(result)
    region_a = str(conf.get("pelias_region_a") or "").strip().upper()[:2]
    if region_a and region_a == expected_subdivision:
        return True
    region = str(conf.get("pelias_region") or "").strip()
    if region and named_location_heads_compatible(expected_subdivision, region):
        return True
    # Fall back to label parse only when structured region is absent.
    if not region_a and not region:
        return False
    return False


def country_agrees(components: dict[str, Any] | None, result: GeocodingResult) -> bool:
    comps = components if isinstance(components, dict) else {}
    expected_country, _sub, _city = jurisdiction_from_components(comps)
    if not expected_country:
        return True
    conf = _confidence(result)
    code = str(conf.get("pelias_country_code") or "").strip().upper()[:2]
    if code and code == expected_country:
        return True
    if code and code != expected_country:
        return False
    return True


def jurisdiction_agrees(components: dict[str, Any] | None, result: GeocodingResult) -> bool:
    return (
        country_agrees(components, result)
        and state_agrees(components, result)
        and city_agrees(components, result)
    )


def poi_names_match(components: dict[str, Any] | None, result: GeocodingResult) -> bool:
    """Exact normalized POI identity (case, punctuation, leading 'the' only)."""
    place_name = place_name_from_components(components)
    if not place_name:
        return False
    conf = _confidence(result)
    pelias_name = str(conf.get("pelias_name") or "").strip()
    if not pelias_name:
        return False
    return named_location_heads_compatible(place_name, pelias_name)


def has_exact_address_evidence(
    components: dict[str, Any] | None,
    result: GeocodingResult,
) -> bool:
    """Street-number evidence plus compatible jurisdiction."""
    if not house_number_matches(components, result):
        return False
    if house_number_conflicts(components, result):
        return False
    return jurisdiction_agrees(components, result)


def has_poi_identity_evidence(
    components: dict[str, Any] | None,
    result: GeocodingResult,
) -> bool:
    """Venue-name identity plus city/state agreement; no house-number conflict."""
    if house_number_conflicts(components, result):
        return False
    if not poi_names_match(components, result):
        return False
    # POI exception requires explicit city and state agreement (fail closed).
    comps = components if isinstance(components, dict) else {}
    if not str(comps.get("city") or "").strip():
        return False
    _country, subdivision, _city = jurisdiction_from_components(comps)
    if not subdivision:
        return False
    if not city_agrees(components, result):
        return False
    if not state_agrees(components, result):
        return False
    if not country_agrees(components, result):
        return False
    return True


def is_decisive_pelias_candidate(
    components: dict[str, Any] | None,
    result: GeocodingResult | None,
) -> bool:
    """True when a Pelias candidate may be auto-accepted under precision-first rules."""
    if result is None or result.result is None:
        return False
    if not is_pelias_geocoder(result.geocoder):
        return False
    if getattr(result.result.geometry, "type", None) != "Point":
        return False
    if house_number_conflicts(components, result):
        return False
    if not country_agrees(components, result):
        return False
    if has_exact_address_evidence(components, result):
        return True
    return has_poi_identity_evidence(components, result)


def _candidate_identity_key(result: GeocodingResult) -> str:
    conf = _confidence(result)
    gid = str(conf.get("pelias_gid") or "").strip()
    if gid:
        return f"gid:{gid}"
    source = str(conf.get("pelias_source") or "").strip()
    source_id = str(conf.get("pelias_source_id") or "").strip()
    if source and source_id:
        return f"src:{source}:{source_id}"
    if result.result is not None and result.result.id:
        return f"id:{result.result.id}"
    coords = ""
    if result.result is not None and getattr(result.result.geometry, "type", None) == "Point":
        coords = ",".join(str(c) for c in result.result.geometry.coordinates)
    name = str(conf.get("pelias_name") or "").strip().lower()
    return f"fallback:{name}:{coords}"


def select_uniquely_decisive_candidate(
    components: dict[str, Any] | None,
    candidates: list[GeocodingResult],
) -> GeocodingResult | None:
    """Return the sole decisive candidate, or None when ambiguous / empty."""
    decisive = [c for c in candidates if is_decisive_pelias_candidate(components, c)]
    if not decisive:
        return None
    identities = {_candidate_identity_key(c) for c in decisive}
    if len(identities) != 1:
        return None
    return decisive[0]


def pelias_poi_result_acceptable(
    components: dict[str, Any] | None,
    geocoding_result: GeocodingResult | None,
) -> bool:
    """Consolidate-gate exception: keep geometry when POI identity evidence is decisive.

    Used only when ``explicit_location_components_match_labels`` fails for a
    ``place`` row (typically missing house number in the display label).
    """
    return is_decisive_pelias_candidate(components, geocoding_result)


def poi_acceptance_is_address_unverified(
    components: dict[str, Any] | None,
    geocoding_result: GeocodingResult | None,
) -> bool:
    """True when acceptance rests on POI identity rather than street-number evidence."""
    if geocoding_result is None:
        return False
    if has_exact_address_evidence(components, geocoding_result):
        return False
    return has_poi_identity_evidence(components, geocoding_result)
