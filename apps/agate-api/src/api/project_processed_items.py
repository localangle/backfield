"""Project-scoped processed-item list and headline/URL search for Agate UI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backfield_db import AgateGraph, AgateProcessedItem, AgateRun, SubstrateArticle
from backfield_entities.public.keyword_query import article_keyword_tsquery
from sqlalchemy import String, cast, func, literal, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Session, col, select

_GENERIC_HEADLINES = frozenset({"article"})
_INPUT_HEADLINE_KEYS = ("headline", "title", "input_headline")
_INPUT_URL_KEYS = ("url",)


@dataclass(frozen=True)
class ProjectProcessedItemRow:
    id: int
    run_id: str
    flow_name: str
    title: str
    url: str | None
    status: str
    created_at: datetime
    source_file: str | None


def _parse_input_obj(input_json: str | None) -> dict[str, Any]:
    if not input_json:
        return {}
    try:
        parsed = json.loads(input_json)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _string_from_input(input_obj: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = input_obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _source_file_label(source_file: str | None) -> str | None:
    if not source_file or source_file.startswith("inline:"):
        return None
    return source_file.rsplit("/", 1)[-1] or source_file


def _display_headline(
    *,
    article_headline: str | None,
    input_obj: dict[str, Any],
) -> str | None:
    input_hl = _string_from_input(input_obj, _INPUT_HEADLINE_KEYS)
    sub_hl = article_headline.strip() if isinstance(article_headline, str) else ""
    if sub_hl and sub_hl.lower() not in _GENERIC_HEADLINES:
        return sub_hl
    return input_hl or (sub_hl or None)


def resolve_project_item_title_and_url(
    *,
    item_id: int,
    source_file: str | None,
    input_json: str | None,
    article_headline: str | None,
    article_url: str | None,
) -> tuple[str, str | None]:
    """Title/URL for a project Articles row (headline primary, source fallback)."""
    input_obj = _parse_input_obj(input_json)
    title = _display_headline(article_headline=article_headline, input_obj=input_obj)
    if not title:
        title = _source_file_label(source_file) or f"Untitled article #{item_id}"

    url = article_url.strip() if isinstance(article_url, str) and article_url.strip() else None
    if not url:
        url = _string_from_input(input_obj, _INPUT_URL_KEYS)
    return title, url


def _json_text_field(column: Any, key: str, *, dialect: str) -> Any:
    if dialect == "postgresql":
        return func.jsonb_extract_path_text(cast(column, JSONB), key)
    return cast(func.json_extract(column, f"$.{key}"), String)


def _headline_url_tsvector() -> Any:
    empty = literal("")
    space = literal(" ")
    document = (
        func.coalesce(SubstrateArticle.headline, empty)
        .op("||")(space)
        .op("||")(func.coalesce(SubstrateArticle.url, empty))
    )
    return func.to_tsvector("english", document)


def _apply_project_item_keyword_filter(stmt: Any, q: str, session: Session) -> Any:
    """Match headline/URL (article or input) and source_file — never article body."""
    pattern = f"%{q.strip()}%"
    bind = session.get_bind()
    dialect = bind.dialect.name

    input_headline = _json_text_field(AgateProcessedItem.input_json, "headline", dialect=dialect)
    input_title = _json_text_field(AgateProcessedItem.input_json, "title", dialect=dialect)
    input_input_headline = _json_text_field(
        AgateProcessedItem.input_json, "input_headline", dialect=dialect
    )
    input_url = _json_text_field(AgateProcessedItem.input_json, "url", dialect=dialect)

    field_matches = [
        AgateProcessedItem.source_file.ilike(pattern),
        input_headline.ilike(pattern),
        input_title.ilike(pattern),
        input_input_headline.ilike(pattern),
        input_url.ilike(pattern),
    ]

    if dialect == "postgresql":
        vector = _headline_url_tsvector()
        ts_query = article_keyword_tsquery(q)
        article_match = vector.op("@@")(ts_query)
        return stmt.where(or_(article_match, *field_matches))

    return stmt.where(
        or_(
            SubstrateArticle.headline.ilike(pattern),
            SubstrateArticle.url.ilike(pattern),
            *field_matches,
        )
    )


def _base_project_items_stmt(project_id: int) -> Any:
    return (
        select(
            AgateProcessedItem.id,
            AgateProcessedItem.run_id,
            AgateGraph.name,
            AgateProcessedItem.status,
            AgateProcessedItem.created_at,
            AgateProcessedItem.source_file,
            AgateProcessedItem.input_json,
            SubstrateArticle.headline,
            SubstrateArticle.url,
        )
        .join(AgateRun, AgateProcessedItem.run_id == AgateRun.id)
        .join(AgateGraph, AgateRun.graph_id == AgateGraph.id)
        .outerjoin(
            SubstrateArticle,
            col(AgateProcessedItem.substrate_article_id) == col(SubstrateArticle.id),
        )
        .where(AgateGraph.project_id == project_id)
    )


def list_project_processed_items(
    session: Session,
    project_id: int,
    *,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ProjectProcessedItemRow], int]:
    """Return recent (or keyword-filtered) processed items for a project."""
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    query = (q or "").strip() or None

    stmt = _base_project_items_stmt(project_id)
    if query:
        stmt = _apply_project_item_keyword_filter(stmt, query, session)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(session.exec(count_stmt).one())

    stmt = (
        stmt.order_by(col(AgateProcessedItem.created_at).desc(), col(AgateProcessedItem.id).desc())
        .offset(offset)
        .limit(limit)
    )
    rows = session.exec(stmt).all()

    out: list[ProjectProcessedItemRow] = []
    for row in rows:
        (
            item_id,
            run_id,
            flow_name,
            status,
            created_at,
            source_file,
            input_json,
            article_headline,
            article_url,
        ) = row
        if item_id is None or not run_id:
            continue
        title, url = resolve_project_item_title_and_url(
            item_id=int(item_id),
            source_file=source_file,
            input_json=input_json,
            article_headline=article_headline,
            article_url=article_url,
        )
        out.append(
            ProjectProcessedItemRow(
                id=int(item_id),
                run_id=str(run_id),
                flow_name=str(flow_name or ""),
                title=title,
                url=url,
                status=str(status),
                created_at=created_at,
                source_file=source_file,
            )
        )
    return out, total
