"""Resolve article text for processed items (substrate read + inline fallback)."""

from __future__ import annotations

from typing import Any

from agate_runtime.nodes.json_input import resolve_document_body_text
from backfield_db import SubstrateArticle
from sqlmodel import Session


def parse_persisted_article_id_from_output(result_obj: dict[str, Any] | None) -> int | None:
    """Article id written by DBOutput on ``stylebook_output`` / legacy keys."""
    if not isinstance(result_obj, dict):
        return None
    for key in ("stylebook_output", "geocode_agent", "place_extract"):
        block = result_obj.get(key)
        if not isinstance(block, dict):
            continue
        raw = block.get("article_id")
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def _parse_input_article_id(input_obj: dict[str, Any]) -> int | None:
    for key in ("input_article_id", "article_id", "substrate_article_id"):
        raw = input_obj.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def _fallback_headline(input_obj: dict[str, Any]) -> str | None:
    for k in ("headline", "title", "input_headline"):
        v = input_obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def build_processed_item_article_context(
    session: Session,
    *,
    project_id: int,
    input_obj: dict[str, Any],
    result_obj: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a dict suitable for :class:`ArticleContextOut` on processed item detail."""
    fallback_body = resolve_document_body_text(input_obj) or ""
    fallback_headline = _fallback_headline(input_obj)

    aid = _parse_input_article_id(input_obj)
    if aid is None:
        aid = parse_persisted_article_id_from_output(result_obj)
    if aid is None:
        if fallback_body:
            return {
                "article_id": None,
                "headline": fallback_headline,
                "body": fallback_body,
                "resolution": "inline_fallback",
                "reason": "no_input_article_id",
            }
        return {
            "article_id": None,
            "headline": fallback_headline,
            "body": "",
            "resolution": "none",
            "reason": "no_input_article_id",
        }

    if project_id <= 0:
        if fallback_body or fallback_headline:
            return {
                "article_id": aid,
                "headline": fallback_headline,
                "body": fallback_body,
                "resolution": "inline_fallback",
                "reason": "no_project_scope_for_article_fetch",
            }
        return {
            "article_id": aid,
            "headline": None,
            "body": "",
            "resolution": "none",
            "reason": "no_project_scope_for_article_fetch",
        }

    art = session.get(SubstrateArticle, aid)
    if art is None:
        return {
            "article_id": aid,
            "headline": fallback_headline,
            "body": fallback_body,
            "resolution": "inline_fallback",
            "reason": "article_not_found",
        }

    if bool(art.deleted):
        return {
            "article_id": aid,
            "headline": fallback_headline,
            "body": fallback_body,
            "resolution": "inline_fallback",
            "reason": "article_deleted",
        }

    if int(art.project_id) != int(project_id):
        return {
            "article_id": aid,
            "headline": fallback_headline,
            "body": fallback_body,
            "resolution": "inline_fallback",
            "reason": "article_project_mismatch",
        }

    rid = art.id
    return {
        "article_id": int(rid) if rid is not None else aid,
        "headline": art.headline,
        "body": art.text,
        "resolution": "substrate",
        "reason": None,
    }
