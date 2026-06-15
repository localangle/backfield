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
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select


class PublicArticleProcessingEntryOut(BaseModel):
    run_id: str
    processed_item_id: int | None = None
    domains: list[str] = Field(default_factory=list)


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


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _persist_block_active(block: Any) -> bool:
    if not isinstance(block, dict):
        return False
    status = block.get("status")
    return isinstance(status, str) and status != "not_present"


def _domains_from_stylebook_output(stylebook_output: dict[str, Any]) -> list[str]:
    domains: list[str] = []
    reconciliation = stylebook_output.get("reconciliation")
    if isinstance(reconciliation, dict):
        domain_summaries = reconciliation.get("domains")
        if isinstance(domain_summaries, list):
            for summary in domain_summaries:
                if isinstance(summary, dict):
                    domain = summary.get("domain")
                    if isinstance(domain, str) and domain:
                        domains.append(domain)
    if _persist_block_active(stylebook_output.get("article_metadata_persist")):
        domains.append("metadata")
    if _persist_block_active(stylebook_output.get("custom_records_persist")):
        domains.append("custom_records")
    if _persist_block_active(stylebook_output.get("image_embeddings_persist")):
        domains.append("image_embeddings")
    return _dedupe_preserve_order(domains)


def _domains_for_processing_entry(
    *,
    run_id: str,
    processed_item: AgateProcessedItem | None,
    meta_run_ids: set[str],
    custom_run_ids: set[str],
) -> list[str]:
    if processed_item and processed_item.result_json:
        try:
            result_obj = json.loads(processed_item.result_json)
        except json.JSONDecodeError:
            result_obj = None
        if isinstance(result_obj, dict):
            stylebook_output = result_obj.get("stylebook_output")
            if isinstance(stylebook_output, dict):
                domains = _domains_from_stylebook_output(stylebook_output)
                if domains:
                    return domains
    fallback: list[str] = []
    if run_id in meta_run_ids:
        fallback.append("metadata")
    if run_id in custom_run_ids:
        fallback.append("custom_records")
    return fallback


def _make_processing_entry(
    *,
    run_id: str,
    processed_item_id: int | None,
    processed_item: AgateProcessedItem | None,
    meta_run_ids: set[str],
    custom_run_ids: set[str],
) -> PublicArticleProcessingEntryOut:
    domains = _domains_for_processing_entry(
        run_id=run_id,
        processed_item=processed_item,
        meta_run_ids=meta_run_ids,
        custom_run_ids=custom_run_ids,
    )
    return PublicArticleProcessingEntryOut(
        run_id=run_id,
        processed_item_id=processed_item_id,
        domains=domains,
    )


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
    meta_run_ids: set[str] = set()
    for run_id in meta_run_rows:
        if run_id:
            run_key = str(run_id)
            meta_run_ids.add(run_key)
            run_ids.add(run_key)

    custom_run_rows = session.exec(
        select(SubstrateCustomRecord.source_run_id)
        .where(
            SubstrateCustomRecord.article_id == article_id,
            SubstrateCustomRecord.source_run_id.isnot(None),
        )
        .distinct()
    ).all()
    custom_run_ids: set[str] = set()
    for run_id in custom_run_rows:
        if run_id:
            run_key = str(run_id)
            custom_run_ids.add(run_key)
            run_ids.add(run_key)

    entries: dict[tuple[str, int | None], PublicArticleProcessingEntryOut] = {}
    processed_items_by_id: dict[int, AgateProcessedItem] = {}

    if run_ids:
        processed_items = session.exec(
            select(AgateProcessedItem).where(col(AgateProcessedItem.run_id).in_(run_ids))
        ).all()
        for item in processed_items:
            if item.id is None or not item.run_id:
                continue
            processed_items_by_id[int(item.id)] = item
            if not _processed_item_references_article(item, article_id=article_id):
                continue
            run_key = str(item.run_id)
            item_id = int(item.id)
            entries[(run_key, item_id)] = _make_processing_entry(
                run_id=run_key,
                processed_item_id=item_id,
                processed_item=item,
                meta_run_ids=meta_run_ids,
                custom_run_ids=custom_run_ids,
            )

    if article.source_run_id:
        run_key = str(article.source_run_id)
        item_id = int(article.source_item_id) if article.source_item_id is not None else None
        processed_item = processed_items_by_id.get(item_id) if item_id is not None else None
        entries[(run_key, item_id)] = _make_processing_entry(
            run_id=run_key,
            processed_item_id=item_id,
            processed_item=processed_item,
            meta_run_ids=meta_run_ids,
            custom_run_ids=custom_run_ids,
        )

    for run_id in sorted(run_ids):
        if not any(entry.run_id == run_id for entry in entries.values()):
            entries[(run_id, None)] = _make_processing_entry(
                run_id=run_id,
                processed_item_id=None,
                processed_item=None,
                meta_run_ids=meta_run_ids,
                custom_run_ids=custom_run_ids,
            )

    return sorted(
        entries.values(),
        key=lambda row: (row.run_id, row.processed_item_id or 0),
        reverse=True,
    )
