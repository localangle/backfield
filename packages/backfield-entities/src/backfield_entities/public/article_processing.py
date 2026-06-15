"""Agate run / processed-item provenance for public article detail."""

from __future__ import annotations

import json
from typing import Any

from backfield_db import (
    AgateProcessedItem,
    SubstrateArticle,
    SubstrateArticleMeta,
    SubstrateCustomRecord,
)
from pydantic import BaseModel
from sqlmodel import Session, col, select


class PublicArticleProcessingEntryOut(BaseModel):
    run_id: str
    processed_item_id: int | None = None


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


def _parse_persisted_article_id_from_output(result_obj: dict[str, Any] | None) -> int | None:
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


def _processed_item_references_article(
    item: AgateProcessedItem,
    *,
    article_id: int,
) -> bool:
    if item.result_json:
        try:
            result_obj = json.loads(item.result_json)
        except json.JSONDecodeError:
            result_obj = None
        if isinstance(result_obj, dict):
            persisted_id = _parse_persisted_article_id_from_output(result_obj)
            if persisted_id == article_id:
                return True
    if item.input_json:
        try:
            input_obj = json.loads(item.input_json)
        except json.JSONDecodeError:
            input_obj = None
        if isinstance(input_obj, dict) and _parse_input_article_id(input_obj) == article_id:
            return True
    return False


def list_public_article_processing(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    article: SubstrateArticle | None = None,
) -> list[PublicArticleProcessingEntryOut]:
    """Return distinct Agate runs (and processed items when known) that touched the article."""
    if article is None:
        article = session.exec(
            select(SubstrateArticle).where(
                SubstrateArticle.id == article_id,
                SubstrateArticle.project_id == project_id,
                SubstrateArticle.deleted == False,  # noqa: E712
            )
        ).first()
    if article is None:
        return []

    run_ids: set[str] = set()
    if article.source_run_id:
        run_ids.add(str(article.source_run_id))

    meta_run_rows = session.exec(
        select(SubstrateArticleMeta.source_run_id)
        .where(
            SubstrateArticleMeta.article_id == article_id,
            SubstrateArticleMeta.source_run_id.isnot(None),
        )
        .distinct()
    ).all()
    for run_id in meta_run_rows:
        if run_id:
            run_ids.add(str(run_id))

    custom_run_rows = session.exec(
        select(SubstrateCustomRecord.source_run_id)
        .where(
            SubstrateCustomRecord.article_id == article_id,
            SubstrateCustomRecord.source_run_id.isnot(None),
        )
        .distinct()
    ).all()
    for run_id in custom_run_rows:
        if run_id:
            run_ids.add(str(run_id))

    entries: dict[tuple[str, int | None], PublicArticleProcessingEntryOut] = {}

    if article.source_run_id:
        run_key = str(article.source_run_id)
        item_id = int(article.source_item_id) if article.source_item_id is not None else None
        entries[(run_key, item_id)] = PublicArticleProcessingEntryOut(
            run_id=run_key,
            processed_item_id=item_id,
        )

    if run_ids:
        processed_items = session.exec(
            select(AgateProcessedItem).where(col(AgateProcessedItem.run_id).in_(run_ids))
        ).all()
        for item in processed_items:
            if item.id is None or not item.run_id:
                continue
            if not _processed_item_references_article(item, article_id=article_id):
                continue
            run_key = str(item.run_id)
            item_id = int(item.id)
            entries[(run_key, item_id)] = PublicArticleProcessingEntryOut(
                run_id=run_key,
                processed_item_id=item_id,
            )

    for run_id in sorted(run_ids):
        if not any(entry.run_id == run_id for entry in entries.values()):
            entries[(run_id, None)] = PublicArticleProcessingEntryOut(
                run_id=run_id,
                processed_item_id=None,
            )

    return sorted(
        entries.values(),
        key=lambda row: (row.run_id, row.processed_item_id or 0),
        reverse=True,
    )
