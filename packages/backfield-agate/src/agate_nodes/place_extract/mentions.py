"""Normalize PlaceExtract ``mentions`` arrays on location dicts."""

from __future__ import annotations

from typing import Any


def parse_mentions_from_location_data(location_data: dict[str, Any]) -> list[dict[str, str]]:
    """Return ``[{ "text": "..." }, ...]`` from raw LLM location object."""
    raw = location_data.get("mentions")
    if not isinstance(raw, list):
        return []

    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        trimmed = text.strip()
        if trimmed:
            out.append({"text": trimmed})
    return out


def normalize_location_mentions(location_data: dict[str, Any]) -> dict[str, Any]:
    """
    Ensure ``mentions`` and ``original_text`` are consistent on a location dict.

    - If ``mentions`` is present, ``original_text`` becomes the first mention text.
    - If only ``original_text`` is present, synthesize ``mentions: [{ text }]``.
    """
    data = dict(location_data)
    mentions = parse_mentions_from_location_data(data)

    original = data.get("original_text")
    original_str = original.strip() if isinstance(original, str) else ""

    if mentions:
        data["mentions"] = mentions
        data["original_text"] = mentions[0]["text"]
        return data

    if original_str:
        data["mentions"] = [{"text": original_str}]
        data["original_text"] = original_str
        return data

    data["mentions"] = []
    return data


def mention_texts_for_persist(entry: dict[str, Any]) -> list[str]:
    """Ordered mention strings for substrate occurrence persistence."""
    normalized = normalize_location_mentions(entry)
    texts: list[str] = []
    for m in normalized.get("mentions") or []:
        if isinstance(m, dict):
            t = m.get("text")
            if isinstance(t, str) and t.strip():
                texts.append(t.strip())
    if texts:
        return texts
    ot = entry.get("original_text")
    if isinstance(ot, str) and ot.strip():
        return [ot.strip()]
    return []
