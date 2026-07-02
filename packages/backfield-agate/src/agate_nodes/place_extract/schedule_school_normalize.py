"""Normalize high-school schedule scoreboard rows from PlaceExtract output."""

from __future__ import annotations

import re
from typing import Any

from agate_nodes.place_extract.article_context import ArticleContext, extract_article_context
from agate_nodes.place_extract.components_build import build_components
from agate_nodes.place_extract.schedule_matchups import (
    extract_schedule_matchups,
    find_schedule_line_for_school,
)

_SCHOOL_NAME_HINTS = (
    " academy",
    " high",
    " school",
    " prep",
    " christian",
    " adventist",
    " catholic",
    " collegiate",
    " institute",
    " seminary",
    " charter",
    " u-high",
    "-ms",
    " ms ",
    " hs ",
)

_MATCHUP_DESCRIPTION_MARKERS = (
    "matchup",
    "scheduled",
    "schedule",
    "game",
    "contest",
    "opponent",
    "listed in",
)


def _normalize_name_key(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _entry_location_str(entry: dict[str, Any]) -> str:
    loc = entry.get("location")
    if isinstance(loc, dict):
        return str(loc.get("full") or "").strip()
    return str(loc or "").strip()


def _entry_type(entry: dict[str, Any]) -> str:
    raw = entry.get("type")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    loc = entry.get("location")
    if isinstance(loc, dict):
        nested = loc.get("type")
        if isinstance(nested, str) and nested.strip():
            return nested.strip().lower()
    return ""


def _entry_components(entry: dict[str, Any]) -> dict[str, Any]:
    components = entry.get("components")
    if isinstance(components, dict):
        return dict(components)
    loc = entry.get("location")
    if isinstance(loc, dict) and isinstance(loc.get("components"), dict):
        return dict(loc["components"])
    return {}


def _primary_school_name(entry: dict[str, Any]) -> str:
    location = _entry_location_str(entry)
    components = _entry_components(entry)
    place = components.get("place")
    if isinstance(place, dict):
        name = str(place.get("name") or "").strip()
        if name:
            return name
    city = str(components.get("city") or "").strip()
    if city and _entry_type(entry) in {"other", "city"}:
        return city
    if location:
        return location.split(",")[0].strip()
    return ""


def appears_in_schedule_matchup(name: str, article_text: str) -> bool:
    key = _normalize_name_key(name)
    if not key:
        return False
    for away, home in extract_schedule_matchups(article_text):
        if key in {_normalize_name_key(away), _normalize_name_key(home)}:
            return True
    return False


def looks_like_school_name(name: str) -> bool:
    token = (name or "").strip().lower()
    if len(token) < 3:
        return False
    return any(hint in token for hint in _SCHOOL_NAME_HINTS)


def _description_suggests_school(entry: dict[str, Any]) -> bool:
    description = str(entry.get("description") or "").lower()
    return any(marker in description for marker in _MATCHUP_DESCRIPTION_MARKERS)


def should_coerce_to_place(entry: dict[str, Any], article_text: str) -> bool:
    loc_type = _entry_type(entry)
    if loc_type not in {"other", "city"}:
        return False
    primary = _primary_school_name(entry)
    if not primary:
        return False
    if appears_in_schedule_matchup(primary, article_text):
        return True
    if looks_like_school_name(primary):
        return True
    return _description_suggests_school(entry)


def _location_with_anchor_state(school_name: str, context: ArticleContext) -> str:
    if "," in school_name:
        return school_name.strip()
    state_abbr = (context.anchor_state_abbr or "").strip()
    if state_abbr:
        return f"{school_name.strip()}, {state_abbr}"
    return school_name.strip()


def coerce_school_location_entry(
    entry: dict[str, Any],
    article_text: str,
    *,
    context: ArticleContext | None = None,
) -> dict[str, Any]:
    """Upgrade mis-typed schedule schools to ``place`` rows with rebuilt components/mentions."""
    if not should_coerce_to_place(entry, article_text):
        return entry

    ctx = context or extract_article_context(article_text)
    out = dict(entry)
    school_name = _primary_school_name(entry)
    new_location = _location_with_anchor_state(school_name, ctx)

    out["type"] = "place"
    out["location"] = new_location
    out["components"] = build_components(new_location, "place", ctx)
    out["components"]["place"] = {
        "name": school_name,
        "addressable": True,
        "natural": False,
    }
    out["components"]["city"] = ""

    from agate_nodes.place_extract.mentions_build import build_mentions

    out["mentions"] = build_mentions(article_text, new_location, "place")
    if out["mentions"]:
        out["original_text"] = out["mentions"][0]["text"]

    if not str(out.get("description") or "").strip():
        out["description"] = f"School listed in a scheduled matchup ({school_name})."
    if not str(out.get("nature") or "").strip() or out.get("nature") == "unknown":
        out["nature"] = "secondary"

    return out


def _new_schedule_school_entry(
    school_name: str,
    article_text: str,
    *,
    context: ArticleContext,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "location": school_name,
        "type": "other",
        "description": f"School listed in a scheduled matchup ({school_name}).",
        "geocode_hints": "",
        "nature": "secondary",
        "nature_secondary_tags": [],
    }
    coerced = coerce_school_location_entry(entry, article_text, context=context)
    return coerced


def normalize_location_entries(
    article_text: str,
    entries: list[dict[str, Any]],
    *,
    context: ArticleContext | None = None,
) -> list[dict[str, Any]]:
    """Coerce schedule schools and add missing ``Team A at Team B`` sides."""
    ctx = context or extract_article_context(article_text)
    normalized = [
        coerce_school_location_entry(entry, article_text, context=ctx) for entry in entries
    ]

    seen = {_normalize_name_key(_primary_school_name(entry)) for entry in normalized}
    seen.discard("")

    for away, home in extract_schedule_matchups(article_text):
        for school_name in (away, home):
            key = _normalize_name_key(school_name)
            if not key or key in seen:
                continue
            normalized.append(_new_schedule_school_entry(school_name, article_text, context=ctx))
            seen.add(key)

    return normalized


def prepare_location_dict_for_geocode(loc: dict[str, Any], article_text: str = "") -> dict[str, Any]:
    """Safety net: remap PlaceExtract-shaped rows before GeocodeAgent type filtering."""
    location_info = loc.get("location")
    if not isinstance(location_info, dict):
        return loc

    entry: dict[str, Any] = {
        "location": str(location_info.get("full") or "").strip(),
        "type": str(location_info.get("type") or "").strip(),
        "components": location_info.get("components") if isinstance(location_info.get("components"), dict) else {},
        "description": loc.get("description", ""),
        "geocode_hints": loc.get("geocode_hints", ""),
        "nature": loc.get("nature", "unknown"),
        "nature_secondary_tags": loc.get("nature_secondary_tags") or [],
        "original_text": loc.get("original_text", ""),
        "mentions": loc.get("mentions") if isinstance(loc.get("mentions"), list) else [],
    }
    text = article_text or str(loc.get("original_text") or "")
    coerced = coerce_school_location_entry(entry, text)

    updated = dict(loc)
    updated_location = dict(location_info)
    updated_location["full"] = _entry_location_str(coerced)
    updated_location["type"] = _entry_type(coerced) or updated_location.get("type", "")
    if isinstance(coerced.get("components"), dict):
        updated_location["components"] = coerced["components"]
    updated["location"] = updated_location
    if coerced.get("mentions"):
        updated["mentions"] = coerced["mentions"]
    if coerced.get("original_text"):
        updated["original_text"] = coerced["original_text"]
    if coerced.get("description"):
        updated["description"] = coerced["description"]
    return updated
