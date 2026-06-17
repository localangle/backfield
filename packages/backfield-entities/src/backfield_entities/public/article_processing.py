"""Agate run / processed-item provenance for public article detail."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    SubstrateArticle,
    SubstrateArticleMeta,
    SubstrateCustomRecord,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.exc import DataError
from sqlmodel import Session, select


class PublicArticleProcessingEntryOut(BaseModel):
    run_id: str
    processed_item_id: int | None = None
    domains: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _ProcessedItemRef:
    id: int
    run_id: str
    result_json: str | None


# Postgres jsonb cannot represent \\u0000 in text extractions; strip the escape before
# casting so rows with null bytes in nested output still match safely.
_SANITIZED_RESULT_JSON = "replace(agate_processed_item.result_json, E'\\\\u0000', '')"
_ARTICLE_ID_JSONB_MATCH = "IN (to_jsonb((:aid)::int), to_jsonb((:aid)::text))"


def _result_json_article_id_match(path: str) -> str:
    return (
        f"({_SANITIZED_RESULT_JSON}::jsonb #> '{path}') {_ARTICLE_ID_JSONB_MATCH}"
    )


def _input_json_article_id_match(field: str) -> str:
    return (
        f"(agate_processed_item.input_json::jsonb -> '{field}') {_ARTICLE_ID_JSONB_MATCH}"
    )


_ARTICLE_REF_SQL = text(
    """
    (
        """
    + _result_json_article_id_match("{stylebook_output,article_id}")
    + """
        OR """
    + _result_json_article_id_match("{geocode_agent,article_id}")
    + """
        OR """
    + _result_json_article_id_match("{place_extract,article_id}")
    + """
        OR """
    + _input_json_article_id_match("input_article_id")
    + """
        OR """
    + _input_json_article_id_match("article_id")
    + """
        OR """
    + _input_json_article_id_match("substrate_article_id")
    + """
    )
    """
)


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
    result_json: str | None,
    meta_run_ids: set[str],
    custom_run_ids: set[str],
) -> list[str]:
    if result_json:
        try:
            result_obj = json.loads(result_json)
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
    result_json: str | None,
    meta_run_ids: set[str],
    custom_run_ids: set[str],
) -> PublicArticleProcessingEntryOut:
    domains = _domains_for_processing_entry(
        run_id=run_id,
        result_json=result_json,
        meta_run_ids=meta_run_ids,
        custom_run_ids=custom_run_ids,
    )
    return PublicArticleProcessingEntryOut(
        run_id=run_id,
        processed_item_id=processed_item_id,
        domains=domains,
    )


def _references_article_from_json(
    result_json: str | None,
    input_json: str | None,
    *,
    article_id: int,
) -> bool:
    if result_json:
        try:
            result_obj = json.loads(result_json)
        except json.JSONDecodeError:
            result_obj = None
        if isinstance(result_obj, dict):
            persisted_id = _parse_persisted_article_id_from_output(result_obj)
            if persisted_id == article_id:
                return True
    if input_json:
        try:
            input_obj = json.loads(input_json)
        except json.JSONDecodeError:
            input_obj = None
        if isinstance(input_obj, dict) and _parse_input_article_id(input_obj) == article_id:
            return True
    return False


def _project_processed_item_json_stmt(project_id: int, *, postgres: bool = False):
    result_json_col = (
        func.replace(AgateProcessedItem.result_json, "\\u0000", "").label("result_json")
        if postgres
        else AgateProcessedItem.result_json
    )
    return (
        select(
            AgateProcessedItem.id,
            AgateProcessedItem.run_id,
            result_json_col,
            AgateProcessedItem.input_json,
        )
        .join(AgateRun, AgateProcessedItem.run_id == AgateRun.id)
        .join(AgateGraph, AgateRun.graph_id == AgateGraph.id)
        .where(AgateGraph.project_id == project_id)
    )


def _processed_items_from_json_rows(
    rows: list[tuple[Any, ...]],
    *,
    article_id: int,
    filter_in_python: bool,
) -> list[_ProcessedItemRef]:
    out: list[_ProcessedItemRef] = []
    for row_id, run_id, result_json, input_json in rows:
        if row_id is None or not run_id:
            continue
        if filter_in_python and not _references_article_from_json(
            result_json, input_json, article_id=article_id
        ):
            continue
        out.append(
            _ProcessedItemRef(id=int(row_id), run_id=str(run_id), result_json=result_json)
        )
    return out


def _fetch_processed_items_referencing_article(
    session: Session,
    *,
    project_id: int,
    article_id: int,
) -> list[_ProcessedItemRef]:
    """Find processed items for this article without loading the whole project batch."""
    aid = str(article_id)
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = _project_processed_item_json_stmt(project_id, postgres=True)
        try:
            rows = session.exec(stmt.where(_ARTICLE_REF_SQL.bindparams(aid=aid))).all()
        except DataError:
            session.rollback()
            rows = session.exec(_project_processed_item_json_stmt(project_id, postgres=True)).all()
            return _processed_items_from_json_rows(
                rows,
                article_id=article_id,
                filter_in_python=True,
            )
        return _processed_items_from_json_rows(
            rows,
            article_id=article_id,
            filter_in_python=False,
        )

    stmt = _project_processed_item_json_stmt(project_id)
    rows = session.exec(stmt).all()
    return _processed_items_from_json_rows(
        rows,
        article_id=article_id,
        filter_in_python=True,
    )


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
    processed_items_by_id: dict[int, _ProcessedItemRef] = {}

    for item in _fetch_processed_items_referencing_article(
        session,
        project_id=project_id,
        article_id=article_id,
    ):
        run_key = str(item.run_id)
        item_id = int(item.id)
        processed_items_by_id[item_id] = item
        entries[(run_key, item_id)] = _make_processing_entry(
            run_id=run_key,
            processed_item_id=item_id,
            result_json=item.result_json,
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
            result_json=processed_item.result_json if processed_item else None,
            meta_run_ids=meta_run_ids,
            custom_run_ids=custom_run_ids,
        )

    for run_id in sorted(run_ids):
        if not any(entry.run_id == run_id for entry in entries.values()):
            entries[(run_id, None)] = _make_processing_entry(
                run_id=run_id,
                processed_item_id=None,
                result_json=None,
                meta_run_ids=meta_run_ids,
                custom_run_ids=custom_run_ids,
            )

    return sorted(
        entries.values(),
        key=lambda row: (row.run_id, row.processed_item_id or 0),
        reverse=True,
    )
