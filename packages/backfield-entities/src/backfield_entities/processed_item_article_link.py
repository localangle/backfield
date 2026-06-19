"""Resolve substrate article ids from Agate processed-item JSON payloads."""

from __future__ import annotations

import json
from typing import Any

_OUTPUT_ARTICLE_ID_BLOCKS = ("stylebook_output", "geocode_agent", "place_extract")
_INPUT_ARTICLE_ID_KEYS = ("input_article_id", "article_id", "substrate_article_id")


def _coerce_article_id(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def substrate_article_id_from_graph_outputs(result_obj: dict[str, Any] | None) -> int | None:
    """Extract persisted article id from immutable graph output keys."""
    if not isinstance(result_obj, dict):
        return None
    for key in _OUTPUT_ARTICLE_ID_BLOCKS:
        block = result_obj.get(key)
        if not isinstance(block, dict):
            continue
        article_id = _coerce_article_id(block.get("article_id"))
        if article_id is not None:
            return article_id
    return None


def substrate_article_id_from_input_obj(input_obj: dict[str, Any] | None) -> int | None:
    if not isinstance(input_obj, dict):
        return None
    for key in _INPUT_ARTICLE_ID_KEYS:
        article_id = _coerce_article_id(input_obj.get(key))
        if article_id is not None:
            return article_id
    return None


def substrate_article_id_from_result_json(result_json: str | None) -> int | None:
    if not result_json:
        return None
    try:
        result_obj = json.loads(result_json)
    except json.JSONDecodeError:
        return None
    return substrate_article_id_from_graph_outputs(result_obj)


def substrate_article_id_from_input_json(input_json: str | None) -> int | None:
    if not input_json:
        return None
    try:
        input_obj = json.loads(input_json)
    except json.JSONDecodeError:
        return None
    return substrate_article_id_from_input_obj(input_obj)


def resolve_substrate_article_id_for_processed_item(
    *,
    result_json: str | None = None,
    input_json: str | None = None,
    outputs: dict[str, Any] | None = None,
) -> int | None:
    """Prefer live graph outputs, then stored result_json, then input_json."""
    if outputs is not None:
        article_id = substrate_article_id_from_graph_outputs(outputs)
        if article_id is not None:
            return article_id
    article_id = substrate_article_id_from_result_json(result_json)
    if article_id is not None:
        return article_id
    return substrate_article_id_from_input_json(input_json)
