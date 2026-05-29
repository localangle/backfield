"""Parse one PersonExtract LLM person entry into ``ExtractedPerson``."""

from __future__ import annotations

from typing import Any

from backfield_stylebook.entities.person.types import PERSON_NATURE_VALUES

from agate_nodes.person_extract.person_schemas import ExtractedPerson, PersonMention


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _normalize_name_from_entry(entry: dict[str, Any]) -> str:
    name_raw = entry.get("name")
    if isinstance(name_raw, str) and name_raw.strip():
        return name_raw.strip()
    if isinstance(name_raw, dict):
        full = _optional_text(name_raw.get("full"))
        if full:
            return full
        first = _optional_text(name_raw.get("first")) or ""
        last = _optional_text(name_raw.get("last")) or ""
        combined = f"{first} {last}".strip()
        if combined:
            return combined
    for alt in ("full_name", "name_full", "fullName"):
        val = _optional_text(entry.get(alt))
        if val:
            return val
    raise ValueError(
        "Missing required field 'name' (string or object with 'full', or 'full_name')"
    )


def _normalize_nature(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip().lower()
    if not s:
        return None
    if s in PERSON_NATURE_VALUES:
        return s
    return "other"


def _parse_nature_secondary_tags(entry: dict[str, Any]) -> list[str]:
    raw = entry.get("nature_secondary_tags")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        tag = item.strip().lower()
        if tag and tag in PERSON_NATURE_VALUES and tag not in out:
            out.append(tag)
    return out


def _parse_mentions(entry: dict[str, Any]) -> list[PersonMention]:
    raw = entry.get("mentions")
    if not isinstance(raw, list):
        raise ValueError("'mentions' field must be a list")
    mentions: list[PersonMention] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                mentions.append(PersonMention(text=text, quote=False))
            continue
        if not isinstance(item, dict):
            raise ValueError("Each mention must be an object with 'text' and 'quote' or a string")
        text = _optional_text(item.get("text")) or _optional_text(item.get("content"))
        if not text:
            continue
        mentions.append(PersonMention(text=text, quote=bool(item.get("quote", False))))
    if not mentions:
        raise ValueError("'mentions' must include at least one non-empty mention")
    return mentions


def person_from_llm_entry(entry: dict[str, Any]) -> ExtractedPerson:
    if not isinstance(entry, dict):
        raise ValueError("person entry must be an object")
    name = _normalize_name_from_entry(entry)
    title = _optional_text(entry.get("title"))
    affiliation = _optional_text(entry.get("affiliation"))
    person_type = _optional_text(entry.get("type"))
    role = _optional_text(entry.get("role_in_story"))
    nature = _normalize_nature(entry.get("nature"))
    secondary = _parse_nature_secondary_tags(entry)
    mentions = _parse_mentions(entry)
    return ExtractedPerson(
        name=name,
        title=title,
        affiliation=affiliation,
        public_figure=bool(entry.get("public_figure")),
        type=person_type,
        role_in_story=role,
        nature=nature,
        nature_secondary_tags=secondary,
        mentions=mentions,
    )
