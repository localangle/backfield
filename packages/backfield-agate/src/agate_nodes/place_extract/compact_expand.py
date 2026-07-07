"""Assemble compact PlaceExtract rows into full location dicts for the existing parse spine."""

from __future__ import annotations

from typing import Any

from agate_nodes.place_extract.article_context import ArticleContext, extract_article_context
from agate_nodes.place_extract.compact_codes import (
    VALID_ADDRESS_PLACE_KINDS,
    expand_nature,
)
from agate_nodes.place_extract.components_build import build_components, normalize_journalistic_block_address
from agate_nodes.place_extract.mentions_build import (
    build_mentions,
    build_mentions_for_evidence_anchor,
)

STREET_LEVEL_TYPES = frozenset(
    {
        "address",
        "intersection_road",
        "intersection_highway",
        "street_road",
        "span",
    }
)


def _infer_address_place_kind(location_type: str) -> str:
    if location_type.startswith("intersection_"):
        return "private_residence"
    if location_type in STREET_LEVEL_TYPES:
        return "unknown"
    return ""


def resolve_address_place_kind(entry: dict[str, Any], location_type: str) -> str:
    """Use LLM-provided address_place_kind when valid; else infer from type."""
    if location_type not in STREET_LEVEL_TYPES:
        return ""
    raw = str(entry.get("address_place_kind") or "").strip().lower()
    if raw in {"", "uk", "unknown"}:
        return _infer_address_place_kind(location_type)
    if raw in VALID_ADDRESS_PLACE_KINDS:
        return raw
    return _infer_address_place_kind(location_type)


def expand_compact_entry(
    article_text: str,
    entry: dict[str, Any],
    *,
    context: ArticleContext | None = None,
) -> dict[str, Any]:
    """Expand one compact row dict into a full location dict for ``place_from_llm_location_entry``."""
    ctx = context or extract_article_context(article_text)
    location = normalize_journalistic_block_address(str(entry.get("location") or "").strip())
    location_type = str(entry.get("type") or "").strip()
    components = build_components(location, location_type, ctx)
    evidence_anchor = str(entry.get("evidence_anchor") or "").strip()
    mentions = build_mentions_for_evidence_anchor(article_text, evidence_anchor)
    if not mentions:
        mentions = build_mentions(article_text, location, location_type)
    nature = expand_nature(str(entry.get("nature") or ""))

    out: dict[str, Any] = {
        "location": location,
        "type": location_type,
        "components": components,
        "mentions": mentions,
        "original_text": mentions[0]["text"] if mentions else "",
        "description": str(entry.get("description") or ""),
        "geocode_hints": str(entry.get("geocode_hints") or ""),
        "nature": nature,
        "nature_secondary_tags": [],
    }
    address_place_kind = resolve_address_place_kind(entry, location_type)
    if location_type in STREET_LEVEL_TYPES and address_place_kind:
        out["address_place_kind"] = address_place_kind
    return out
