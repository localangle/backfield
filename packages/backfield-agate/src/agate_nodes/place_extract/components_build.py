"""Deterministic PlaceExtract components builder for compact expansion."""

from __future__ import annotations

import re
from typing import Any

import us
import usaddress

from agate_nodes.place_extract.article_context import ArticleContext, state_components
from agate_nodes.place_extract.location_utils import US_STATES, split_location_parts

NATURAL_PLACE_TOKENS = (
    "park",
    "lake",
    "river",
    "beach",
    "forest",
    "mountain",
    "canyon",
    "bay",
    "ocean",
    "sea",
    "gulf",
    "creek",
    "falls",
    "trail",
    "wilderness",
    "national park",
)

SPAN_BETWEEN_RE = re.compile(
    r"^(?P<street>.+?)\s+between\s+(?P<start>.+?)\s+and\s+(?P<end>.+)$",
    flags=re.IGNORECASE,
)
SPAN_TO_RE = re.compile(
    r"^(?P<street>.+?)\s+(?:from\s+)?(?P<start>.+?)\s+to\s+(?P<end>.+)$",
    flags=re.IGNORECASE,
)


def _empty_components() -> dict[str, Any]:
    return {
        "place": {},
        "street_road": {},
        "span": {},
        "address": "",
        "neighborhood": "",
        "city": "",
        "county": "",
        "state": {"name": "", "abbr": ""},
        "country": {"name": "United States", "abbr": "US"},
    }


def _normalize_state_abbr(value: str) -> str:
    token = (value or "").strip()
    if not token:
        return ""
    if len(token) == 2 and token.upper() in US_STATES:
        return token.upper()
    try:
        state = us.states.lookup(token)
    except AttributeError:
        state = None
    if state is not None:
        return str(getattr(state, "abbr", "") or "").upper()
    return token.upper() if token.upper() in US_STATES else ""


def _state_name(abbr: str) -> str:
    if not abbr:
        return ""
    return US_STATES.get(abbr, "")


def _parse_location_parts(location: str) -> tuple[list[str], str, str, str]:
    parts = split_location_parts(location)
    state_abbr = ""
    city = ""
    county = ""

    if parts and parts[-1].upper() in US_STATES:
        state_abbr = parts[-1].upper()
        parts = parts[:-1]

    if parts and re.search(r"\bcounty\b", parts[-1], flags=re.IGNORECASE):
        county = parts[-1]
        parts = parts[:-1]

    if parts:
        city = parts[-1]
        parts = parts[:-1]

    return parts, city, state_abbr, county


def _usaddress_tag(location: str) -> tuple[dict[str, str], str]:
    try:
        tagged, label = usaddress.tag(location)
    except usaddress.RepeatedLabelError:
        return {}, ""
    if not isinstance(tagged, dict):
        return {}, label
    return {str(k): str(v) for k, v in tagged.items()}, label


_ADDRESS_TOKEN_ORDER = (
    "AddressNumber",
    "AddressNumberPrefix",
    "AddressNumberSuffix",
    "StreetNamePreModifier",
    "StreetNamePreDirectional",
    "StreetNamePreType",
    "StreetName",
    "StreetNamePostType",
    "StreetNamePostDirectional",
    "OccupancyType",
    "OccupancyIdentifier",
)


def _format_usaddress(tagged: dict[str, str]) -> str:
    if not tagged:
        return ""
    parts = [tagged[key] for key in _ADDRESS_TOKEN_ORDER if tagged.get(key)]
    return " ".join(parts).strip()


def _has_address_number(tagged: dict[str, str]) -> bool:
    return bool(tagged.get("AddressNumber"))


def _is_natural_place(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in NATURAL_PLACE_TOKENS)


def _extract_address_from_location(
    location: str,
    *,
    city: str,
    state_abbr: str,
    extra_segments: list[str] | None = None,
) -> str:
    """Find a mailing-style address in a location string or its middle segments."""
    candidates: list[str] = []
    for segment in extra_segments or []:
        cleaned = segment.strip()
        if not cleaned:
            continue
        candidates.append(cleaned)
        with_city = ", ".join(part for part in [cleaned, city, state_abbr] if part)
        if with_city != cleaned:
            candidates.append(with_city)
    if location.strip():
        candidates.append(location.strip())

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        tagged, label = _usaddress_tag(candidate)
        if _has_address_number(tagged):
            formatted = _format_usaddress(tagged)
            if formatted:
                return formatted
    return ""


def _span_endpoints(primary: str, city: str, state_abbr: str) -> dict[str, Any]:
    match = SPAN_BETWEEN_RE.match(primary.strip())
    if not match:
        match = SPAN_TO_RE.match(primary.strip())
    if not match:
        return {}

    start = match.group("start").strip(" ,.")
    end = match.group("end").strip(" ,.")
    suffix = ", ".join(part for part in [city, state_abbr] if part)

    def endpoint(location: str) -> dict[str, str]:
        loc = location
        if suffix and suffix.lower() not in location.lower():
            loc = f"{location}, {suffix}"
        return {"type": "intersection", "location": loc}

    return {"start": endpoint(start), "end": endpoint(end)}


def _neighborhood_from_parts(
    *,
    parts: list[str],
    location_type: str,
) -> str:
    if location_type == "neighborhood":
        return parts[0] if parts else ""
    if location_type in {"region_city", "neighborhood"} and len(parts) >= 2:
        return parts[0]
    return ""


def build_components(
    location: str,
    location_type: str,
    context: ArticleContext,
) -> dict[str, Any]:
    """Build production-shaped components deterministically from a location string."""
    components = _empty_components()
    parts, city, state_abbr, county_from_parts = _parse_location_parts(location)

    if not state_abbr:
        inferred = state_components(location, context)
        state_abbr = inferred.get("abbr") or context.anchor_state_abbr or ""
    components["state"] = {"name": _state_name(state_abbr), "abbr": state_abbr}
    components["city"] = city

    primary = parts[0] if parts else location.split(",")[0].strip()
    if location_type == "city":
        components["city"] = primary
        primary = ""
    elif location_type == "state":
        components["city"] = ""
        if not state_abbr:
            state_abbr = _normalize_state_abbr(primary)
            components["state"] = {"name": _state_name(state_abbr), "abbr": state_abbr}

    neighborhood = _neighborhood_from_parts(parts=parts, location_type=location_type)
    if neighborhood:
        components["neighborhood"] = neighborhood

    if county_from_parts:
        components["county"] = county_from_parts
    elif location_type == "county":
        components["county"] = primary if "county" in primary.lower() else f"{primary} County"

    street_segment = primary
    tagged, label = _usaddress_tag(street_segment)
    if not tagged and street_segment:
        tagged, label = _usaddress_tag(
            ", ".join(part for part in [street_segment, components["city"], state_abbr] if part)
        )
    formatted_address = _format_usaddress(tagged)

    if location_type == "place":
        place_name = primary or location.split(",")[0].strip()
        embedded_address = _extract_address_from_location(
            location,
            city=components["city"],
            state_abbr=state_abbr,
            extra_segments=parts[1:],
        )
        is_natural = _is_natural_place(place_name)
        components["place"] = {
            "name": place_name,
            "natural": is_natural,
            "addressable": bool(embedded_address) or not is_natural,
        }
        if embedded_address:
            components["address"] = embedded_address
    elif location_type == "street_road":
        street_name = primary
        boundary = ", ".join(part for part in [components["city"], state_abbr] if part)
        components["street_road"] = {"name": street_name, "boundary": boundary}
        if formatted_address and _has_address_number(tagged):
            components["address"] = formatted_address
        elif street_name:
            components["address"] = street_name
    elif location_type == "span":
        street_name = primary
        boundary = ", ".join(part for part in [components["city"], state_abbr] if part)
        components["street_road"] = {"name": street_name, "boundary": boundary}
        span = _span_endpoints(primary, components["city"], state_abbr)
        if span:
            components["span"] = span
    elif location_type in {"address", "intersection_road", "intersection_highway"}:
        if _has_address_number(tagged) and formatted_address:
            components["address"] = formatted_address
        elif location_type == "address" and primary:
            components["address"] = primary
    elif location_type == "neighborhood":
        components["neighborhood"] = primary
    elif location_type == "region_city":
        components["neighborhood"] = primary
        if not components["city"] and context.anchor_city:
            components["city"] = context.anchor_city
    elif location_type == "county" and not components["county"]:
        components["county"] = primary if "county" in primary.lower() else f"{primary} County"

    return components
