"""Deterministic PlaceExtract components builder for compact expansion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import pycountry
import usaddress

from agate_nodes.place_extract.article_context import ArticleContext
from agate_nodes.place_extract.location_utils import split_location_parts

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
_BLOCK_OF_RE = re.compile(r"(\d+)\s+block\s+of\s+", flags=re.IGNORECASE)
_STREET_TYPE_ABBREVS = (
    (re.compile(r"\bAvenue\b", flags=re.IGNORECASE), "Ave"),
    (re.compile(r"\bStreet\b", flags=re.IGNORECASE), "St"),
    (re.compile(r"\bBoulevard\b", flags=re.IGNORECASE), "Blvd"),
    (re.compile(r"\bRoad\b", flags=re.IGNORECASE), "Rd"),
)
_DIRECTION_ABBREVS = (
    (re.compile(r"\bSouth\b", flags=re.IGNORECASE), "S"),
    (re.compile(r"\bNorth\b", flags=re.IGNORECASE), "N"),
    (re.compile(r"\bEast\b", flags=re.IGNORECASE), "E"),
    (re.compile(r"\bWest\b", flags=re.IGNORECASE), "W"),
)
_US_ZIP_RE = re.compile(r"(?<!\d)(\d{5}(?:-\d{4})?)$", flags=re.IGNORECASE)
_CANADIAN_POSTAL_RE = re.compile(
    r"(?<![A-Z0-9])([ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ -]?\d[ABCEGHJ-NPRSTV-Z]\d)$",
    flags=re.IGNORECASE,
)
_UK_POSTAL_RE = re.compile(
    r"(?<![A-Z0-9])((?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}))$",
    flags=re.IGNORECASE,
)
_GENERAL_POSTAL_RE = re.compile(
    r"(?<![A-Z0-9])([A-Z]{0,2}\d[A-Z0-9-]*(?:[ -][A-Z0-9]{2,4})?)$",
    flags=re.IGNORECASE,
)
_COUNTRY_ALIASES = {
    "u.s.": "US",
    "u.s.a.": "US",
    "usa": "US",
    "united states of america": "US",
    "uk": "GB",
    "u.k.": "GB",
}


@dataclass(frozen=True)
class _Country:
    name: str
    abbr: str


@dataclass(frozen=True)
class _Subdivision:
    name: str
    abbr: str
    country_abbr: str


@dataclass(frozen=True)
class _ParsedLocation:
    parts: list[str]
    city: str
    county: str
    subdivision: _Subdivision | None
    country: _Country
    postal_code: str
    country_was_explicit: bool


def normalize_journalistic_block_address(location: str) -> str:
    """Convert ``6500 block of South Hermitage Avenue`` to ``6500 S Hermitage Ave``."""
    if not _BLOCK_OF_RE.search(location):
        return location
    parts = [part.strip() for part in location.split(",") if part.strip()]
    if not parts:
        return location
    head = _BLOCK_OF_RE.sub(r"\1 ", parts[0], count=1)
    for pattern, replacement in _DIRECTION_ABBREVS:
        head = pattern.sub(replacement, head)
    for pattern, replacement in _STREET_TYPE_ABBREVS:
        head = pattern.sub(replacement, head)
    return ", ".join([head, *parts[1:]])


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
        "postal_code": "",
    }


@lru_cache(maxsize=256)
def _lookup_country(value: str) -> _Country | None:
    token = value.strip()
    if not token:
        return None
    lookup_value = _COUNTRY_ALIASES.get(token.casefold(), token)
    try:
        record = pycountry.countries.lookup(lookup_value)
    except LookupError:
        return None
    name = str(getattr(record, "common_name", "") or getattr(record, "name", "")).strip()
    abbr = str(getattr(record, "alpha_2", "")).strip().upper()
    if not name or not abbr:
        return None
    return _Country(name=name, abbr=abbr)


@lru_cache(maxsize=1)
def _subdivisions() -> tuple[_Subdivision, ...]:
    subdivisions: list[_Subdivision] = []
    for record in pycountry.subdivisions:
        code = str(getattr(record, "code", "")).strip().upper()
        name = str(getattr(record, "name", "")).strip()
        country_abbr = str(getattr(record, "country_code", "")).strip().upper()
        if not code or not name or not country_abbr:
            continue
        subdivisions.append(
            _Subdivision(
                name=name,
                abbr=code.split("-", 1)[-1],
                country_abbr=country_abbr,
            )
        )
    return tuple(subdivisions)


def _normalized_jurisdiction_token(value: str) -> str:
    return re.sub(r"[.\s-]+", " ", value.strip()).casefold()


def _lookup_subdivision(value: str, country_abbr: str | None) -> _Subdivision | None:
    normalized = _normalized_jurisdiction_token(value)
    if not normalized:
        return None
    matches = [
        subdivision
        for subdivision in _subdivisions()
        if (not country_abbr or subdivision.country_abbr == country_abbr)
        and normalized
        in {
            _normalized_jurisdiction_token(subdivision.name),
            _normalized_jurisdiction_token(subdivision.abbr),
        }
    ]
    if len(matches) == 1:
        return matches[0]
    if not country_abbr:
        us_matches = [match for match in matches if match.country_abbr == "US"]
        if len(us_matches) == 1:
            return us_matches[0]
    return None


def _postal_pattern(country_abbr: str | None) -> tuple[re.Pattern[str], str | None]:
    if country_abbr == "US":
        return _US_ZIP_RE, "US"
    if country_abbr == "CA":
        return _CANADIAN_POSTAL_RE, "CA"
    if country_abbr == "GB":
        return _UK_POSTAL_RE, "GB"
    return _GENERAL_POSTAL_RE, None


def _extract_postal_code(value: str, country_abbr: str | None) -> tuple[str, str, str | None]:
    patterns: list[tuple[re.Pattern[str], str | None]]
    if country_abbr:
        patterns = [_postal_pattern(country_abbr)]
    else:
        patterns = [
            (_CANADIAN_POSTAL_RE, "CA"),
            (_UK_POSTAL_RE, "GB"),
            (_US_ZIP_RE, "US"),
            (_GENERAL_POSTAL_RE, None),
        ]
    for pattern, inferred_country in patterns:
        match = pattern.search(value.strip())
        if not match:
            continue
        postal_code = re.sub(r"\s+", " ", match.group(1).upper()).strip()
        remainder = value[: match.start(1)].rstrip(" ,")
        return remainder, postal_code, inferred_country
    return value, "", None


def _country_for_subdivision(subdivision: _Subdivision | None) -> _Country | None:
    if subdivision is None:
        return None
    return _lookup_country(subdivision.country_abbr)


def _parse_location_parts(
    location: str,
    location_type: str,
    context: ArticleContext,
) -> _ParsedLocation:
    parts = split_location_parts(location)
    explicit_country: _Country | None = None
    subdivision: _Subdivision | None = None
    postal_code = ""
    city = ""
    county = ""

    if parts:
        country_candidate = _lookup_country(parts[-1])
        subdivision_candidate = _lookup_subdivision(parts[-1], None)
        prefer_subdivision = subdivision_candidate is not None and (
            location_type == "state"
            or (location_type != "country" and len(parts[-1].strip()) <= 3)
        )
        if country_candidate is not None and not prefer_subdivision:
            explicit_country = country_candidate
            parts = parts[:-1]

    country = explicit_country
    if parts:
        remainder, postal_code, postal_country = _extract_postal_code(
            parts[-1],
            country.abbr if country else None,
        )
        if postal_code:
            if remainder:
                parts[-1] = remainder
            else:
                parts = parts[:-1]
            if country is None and postal_country:
                country = _lookup_country(postal_country)

    if parts and (location_type == "state" or len(parts) >= 2):
        subdivision = _lookup_subdivision(parts[-1], country.abbr if country else None)
    if subdivision is not None:
        parts = parts[:-1]

    if parts and re.search(r"\bcounty\b", parts[-1], flags=re.IGNORECASE):
        county = parts[-1]
        parts = parts[:-1]

    if parts:
        city = parts[-1]
        parts = parts[:-1]

    if country is None:
        country = _country_for_subdivision(subdivision)
    if country is None:
        country = _lookup_country("US")
    if country is None:
        raise RuntimeError("ISO country data does not include the United States")

    if subdivision is None and not explicit_country:
        inferred_abbr = context.state_for_city(city) if city else context.anchor_state_abbr
        subdivision = _lookup_subdivision(inferred_abbr, "US")

    return _ParsedLocation(
        parts=parts,
        city=city,
        county=county,
        subdivision=subdivision,
        country=country,
        postal_code=postal_code,
        country_was_explicit=explicit_country is not None,
    )


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
    location = normalize_journalistic_block_address(location)
    components = _empty_components()
    parsed = _parse_location_parts(location, location_type, context)
    parts = parsed.parts
    state_abbr = parsed.subdivision.abbr if parsed.subdivision else ""
    components["state"] = {
        "name": parsed.subdivision.name if parsed.subdivision else "",
        "abbr": state_abbr,
    }
    components["country"] = {
        "name": parsed.country.name,
        "abbr": parsed.country.abbr,
    }
    components["postal_code"] = parsed.postal_code
    components["city"] = parsed.city

    primary = parts[0] if parts else location.split(",")[0].strip()
    if location_type == "city":
        components["city"] = primary
        primary = ""
    elif location_type == "state":
        components["city"] = ""
    elif location_type == "country":
        components["city"] = ""
        components["state"] = {"name": "", "abbr": ""}
        primary = ""

    neighborhood = _neighborhood_from_parts(parts=parts, location_type=location_type)
    if neighborhood:
        components["neighborhood"] = neighborhood

    if parsed.county:
        components["county"] = parsed.county
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
