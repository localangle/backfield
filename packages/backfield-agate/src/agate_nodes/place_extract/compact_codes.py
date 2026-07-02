"""Short enum codes for compact PlaceExtract array output."""

from __future__ import annotations

from backfield_entities.entities.location.types import PLACE_EXTRACT_LOCATION_TYPES

VALID_TYPES = frozenset(PLACE_EXTRACT_LOCATION_TYPES)
VALID_NATURES = frozenset({"primary", "secondary", "subject", "context", "person", "unknown"})
VALID_ADDRESS_PLACE_KINDS = frozenset({"public_named", "private_residence", "unknown"})

LOCATION_TYPE_TO_CODE: dict[str, str] = {
    "place": "pl",
    "address": "ad",
    "intersection_road": "ir",
    "intersection_highway": "ih",
    "street_road": "sr",
    "span": "sp",
    "neighborhood": "nb",
    "region_city": "rg",
    "city": "ci",
    "county": "cn",
    "region_state": "rs",
    "state": "st",
    "region_national": "rn",
    "country": "cy",
    "political_district": "pd",
    "natural": "nt",
    "other": "ot",
}

LOCATION_TYPE_FROM_CODE: dict[str, str] = {
    code: name for name, code in LOCATION_TYPE_TO_CODE.items()
}

NATURE_TO_CODE: dict[str, str] = {
    "primary": "p",
    "secondary": "s",
    "subject": "j",
    "context": "c",
    "person": "r",
    "unknown": "u",
}

NATURE_FROM_CODE: dict[str, str] = {code: name for name, code in NATURE_TO_CODE.items()}

ADDRESS_PLACE_KIND_TO_CODE: dict[str, str] = {
    "public_named": "pn",
    "private_residence": "pv",
    "unknown": "uk",
}

ADDRESS_PLACE_KIND_FROM_CODE: dict[str, str] = {
    code: name for name, code in ADDRESS_PLACE_KIND_TO_CODE.items()
}

COMPACT_CODE_LEGEND = """\
Use these short codes in array columns 2–4 (type, nature, address_place_kind):

type (column 2):
  pl place  ad address  ir intersection_road  ih intersection_highway
  sr street_road  sp span  nb neighborhood  rg region_city  ci city
  cn county  rs region_state  st state  rn region_national  cy country
  pd political_district  nt natural  ot other

nature (column 3):
  p primary  s secondary  j subject  c context  r person  u unknown

address_place_kind (column 4; use "" when not street-level):
  pn public_named  pv private_residence  uk unknown
"""


def expand_location_type(value: str) -> str:
    token = (value or "").strip().lower()
    if not token:
        return ""
    if token in VALID_TYPES:
        return token
    expanded = LOCATION_TYPE_FROM_CODE.get(token)
    if expanded:
        return expanded
    return token


def expand_nature(value: str) -> str:
    token = (value or "").strip().lower()
    if not token:
        return "unknown"
    if token in VALID_NATURES:
        return token
    expanded = NATURE_FROM_CODE.get(token)
    if expanded:
        return expanded
    return "unknown"


def expand_address_place_kind(value: str) -> str:
    token = (value or "").strip().lower()
    if not token:
        return ""
    if token in VALID_ADDRESS_PLACE_KINDS:
        return token
    expanded = ADDRESS_PLACE_KIND_FROM_CODE.get(token)
    if expanded:
        return expanded
    return token


def expand_row_enum_fields(entry: dict[str, str]) -> dict[str, str]:
    """Expand compressed enum columns in a compact location dict."""
    expanded = dict(entry)
    if "type" in expanded:
        expanded["type"] = expand_location_type(str(expanded["type"]))
    if "nature" in expanded:
        expanded["nature"] = expand_nature(str(expanded["nature"]))
    if "address_place_kind" in expanded:
        expanded["address_place_kind"] = expand_address_place_kind(
            str(expanded["address_place_kind"])
        )
    return expanded
