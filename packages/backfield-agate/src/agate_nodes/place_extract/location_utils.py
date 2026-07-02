"""Shared location-string helpers for PlaceExtract compact expansion."""

from __future__ import annotations

import re

US_STATES: dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}

US_STATE_ABBR_BY_NAME: dict[str, str] = {
    name.lower(): abbr for abbr, name in US_STATES.items()
}

_FORBIDDEN_CITY_PREFIX = r"(?:In|On|At|And|Of|The|Near|By)\b"
_CITY_WORD = r"(?-i:[A-Z][a-z'.-]+|[A-Z]{2,})"
CITY_NAME_PATTERN = (
    rf"(?!{_FORBIDDEN_CITY_PREFIX}){_CITY_WORD}"
    rf"(?:\s+(?!in\b|on\b|the\b|of\b|at\b|and\b){_CITY_WORD}){{0,3}}"
)
STATE_NAME_PATTERN = "|".join(re.escape(name) for name in US_STATES.values())
CITY_STATE_ABBR_RE = re.compile(rf"\b({CITY_NAME_PATTERN}),\s*([A-Z]{{2}})\b")
CITY_STATE_NAME_RE = re.compile(
    rf"\b({CITY_NAME_PATTERN}),\s*({STATE_NAME_PATTERN})\b",
    flags=re.IGNORECASE,
)


def title_location(text: str) -> str:
    return " ".join(part.capitalize() if part.isupper() else part for part in text.split())


def split_location_parts(location: str) -> list[str]:
    return [part.strip() for part in location.split(",") if part.strip()]


def location_has_state_suffix(parts: list[str]) -> bool:
    return bool(parts) and parts[-1].upper() in US_STATES


def parse_city_state_pairs(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for city, abbr in CITY_STATE_ABBR_RE.findall(text):
        if abbr.upper() in US_STATES:
            pairs.append((title_location(city.strip()), abbr.upper()))
    for city, state_name in CITY_STATE_NAME_RE.findall(text):
        abbr = US_STATE_ABBR_BY_NAME.get(state_name.lower())
        if abbr:
            pairs.append((title_location(city.strip()), abbr))
    return pairs
