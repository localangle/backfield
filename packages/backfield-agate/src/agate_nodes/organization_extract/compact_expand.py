"""Compact OrganizationExtract array rows → dict entries for organization_from_llm_entry."""

from __future__ import annotations

from typing import Any

from backfield_entities.entities.organization.review import _BOUNDARY_VALUE_BY_SHORT
from backfield_entities.entities.organization.types import (
    ORGANIZATION_NATURE_VALUES,
    ORGANIZATION_TYPE_VALUES,
)

ORG_TYPE_CODES: dict[str, str] = {
    "government": "gov",
    "law_enforcement": "le",
    "court": "crt",
    "legislative_body": "leg",
    "political_party": "pp",
    "school_district": "sd",
    "school": "sch",
    "university": "uni",
    "hospital": "hos",
    "public_health": "ph",
    "public_services": "psv",
    "utilities": "uti",
    "company": "co",
    "local_business": "lb",
    "financial_institution": "fin",
    "real_estate": "re",
    "nonprofit": "np",
    "community_group": "cg",
    "religious_org": "rel",
    "culture_arts": "ca",
    "sports_team": "st",
    "sports_league": "sl",
    "media": "med",
    "other": "oth",
}

ORG_TYPE_FROM_CODE: dict[str, str] = {
    code: slug for slug, code in ORG_TYPE_CODES.items()
}

ORG_NATURE_CODES: dict[str, str] = {
    "primary": "pr",
    "actor": "ac",
    "source": "so",
    "subject": "su",
    "affected": "af",
    "regulator": "rg",
    "context": "cx",
    "other": "ot",
}

ORG_NATURE_FROM_CODE: dict[str, str] = {
    code: slug for slug, code in ORG_NATURE_CODES.items()
}

ORG_COMPACT_LEGEND = """\
Use these short codes in array columns 1 and 3 (type, nature):

type (column 1):
  gov government  le law_enforcement  crt court  leg legislative_body  pp political_party
  sd school_district  sch school  uni university  hos hospital  ph public_health
  psv public_services  uti utilities  co company  lb local_business  fin financial_institution
  re real_estate  np nonprofit  cg community_group  rel religious_org  ca culture_arts
  st sports_team  sl sports_league  med media  oth other

nature (column 3):
  pr primary  ac actor  so source  su subject  af affected  rg regulator  cx context  ot other

extras (optional trailing object; omit when empty):
  b — boundary short name: brand_platform, work_title, place_business, event_competition
  st — array of nature codes for nature_secondary_tags
"""


def expand_organization_type(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return "other"
    if token in ORGANIZATION_TYPE_VALUES:
        return token
    expanded = ORG_TYPE_FROM_CODE.get(token)
    if expanded:
        return expanded
    return token


def expand_organization_nature(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return "other"
    if token in ORGANIZATION_NATURE_VALUES:
        return token
    expanded = ORG_NATURE_FROM_CODE.get(token)
    if expanded:
        return expanded
    return token


def expand_organization_boundary(value: Any) -> str | None:
    if value is None:
        return None
    token = str(value).strip().lower()
    if not token:
        return None
    full = _BOUNDARY_VALUE_BY_SHORT.get(token)
    if full:
        return full
    if token in {
        "borderline_brand_platform",
        "borderline_work_title",
        "borderline_place_business",
        "borderline_event_competition",
    }:
        return token
    return token


def _coerce_bool_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _parse_mentions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValueError("'mentions' field must be a list")
    mentions: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                mentions.append({"text": text, "quote": False})
            continue
        if isinstance(item, list) and len(item) >= 1:
            text = str(item[0] or "").strip()
            if not text:
                continue
            quote = _coerce_bool_flag(item[1]) if len(item) > 1 else False
            mentions.append({"text": text, "quote": quote})
            continue
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("content") or "").strip()
            if text:
                mentions.append({"text": text, "quote": bool(item.get("quote", False))})
            continue
        raise ValueError("Each mention must be [text, quote] or an object with 'text' and 'quote'")
    return mentions


def _expand_nature_code_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        slug = expand_organization_nature(item)
        if slug in ORGANIZATION_NATURE_VALUES and slug not in out:
            out.append(slug)
    return out


def _apply_organization_extras(entry: dict[str, Any], extras: dict[str, Any]) -> None:
    boundary = expand_organization_boundary(extras.get("b"))
    if boundary:
        entry["organization_boundary"] = boundary

    secondary = _expand_nature_code_list(extras.get("st"))
    if secondary:
        entry["nature_secondary_tags"] = secondary


def expand_compact_organization_row(row: list[Any]) -> dict[str, Any]:
    """Expand one compact organization array row into a dict for ``organization_from_llm_entry``."""
    if not isinstance(row, list):
        raise ValueError("organization entry must be an array")
    if not row:
        raise ValueError("organization entry array must not be empty")

    name = str(row[0] or "").strip()
    if not name:
        raise ValueError("Missing required field 'name'")

    type_code = row[1] if len(row) > 1 else "oth"
    role_in_story = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
    nature_code = row[3] if len(row) > 3 else "ot"
    mentions_raw = row[4] if len(row) > 4 else []

    entry: dict[str, Any] = {
        "name": name,
        "type": expand_organization_type(type_code),
        "role_in_story": role_in_story,
        "nature": expand_organization_nature(nature_code),
        "mentions": _parse_mentions(mentions_raw),
    }

    if len(row) > 5 and isinstance(row[5], dict):
        _apply_organization_extras(entry, row[5])

    return entry
