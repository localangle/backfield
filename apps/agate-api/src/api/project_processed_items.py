"""Project-scoped processed-item list and headline/URL search for Agate UI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backfield_db import AgateGraph, AgateProcessedItem, AgateRun, SubstrateArticle
from backfield_entities.public.keyword_query import article_keyword_tsquery
from sqlalchemy import String, case, cast, func, literal, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import aliased
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
    processing_count: int
    article_id: int | None


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


_ROW_FIELDS = (
    "item_id",
    "run_id",
    "flow_name",
    "status",
    "created_at",
    "source_file",
    "input_json",
    "article_headline",
    "article_url",
    "resolved_article_id",
)


def _normalized_sql_url(url_expr: Any) -> Any:
    return func.nullif(func.lower(func.trim(url_expr)), "")


def _prefixed_key(prefix: str, value: Any) -> Any:
    return literal(prefix).op("||")(cast(value, String))


def _input_url_norm(dialect: str) -> Any:
    return _normalized_sql_url(
        _json_text_field(AgateProcessedItem.input_json, "url", dialect=dialect)
    )


def _project_items_select(session: Session, project_id: int) -> Any:
    """Project processings with a story group key and resolved article id.

    Group key precedence: saved article id, then the project article with the same
    URL, then the normalized URL, then the processed item alone.
    """
    dialect = session.get_bind().dialect.name
    input_url_norm = _input_url_norm(dialect)
    article_by_url = aliased(SubstrateArticle)
    matched_article_id = (
        select(article_by_url.id)
        .where(
            article_by_url.project_id == project_id,
            _normalized_sql_url(article_by_url.url) == _input_url_norm(dialect),
        )
        .order_by(col(article_by_url.id).asc())
        .limit(1)
        .correlate_except(article_by_url)
        .scalar_subquery()
    )
    resolved_article_id = case(
        (
            AgateProcessedItem.substrate_article_id.is_not(None),
            AgateProcessedItem.substrate_article_id,
        ),
        else_=matched_article_id,
    )
    group_key = case(
        (
            AgateProcessedItem.substrate_article_id.is_not(None),
            _prefixed_key("article:", AgateProcessedItem.substrate_article_id),
        ),
        (
            matched_article_id.is_not(None),
            _prefixed_key("article:", matched_article_id),
        ),
        (
            input_url_norm.is_not(None),
            _prefixed_key("url:", input_url_norm),
        ),
        else_=_prefixed_key("item:", AgateProcessedItem.id),
    )
    return (
        select(
            AgateProcessedItem.id.label("item_id"),
            AgateProcessedItem.run_id.label("run_id"),
            AgateGraph.name.label("flow_name"),
            AgateProcessedItem.status.label("status"),
            AgateProcessedItem.created_at.label("created_at"),
            AgateProcessedItem.source_file.label("source_file"),
            AgateProcessedItem.input_json.label("input_json"),
            SubstrateArticle.headline.label("article_headline"),
            SubstrateArticle.url.label("article_url"),
            group_key.label("group_key"),
            resolved_article_id.label("resolved_article_id"),
        )
        .join(AgateRun, AgateProcessedItem.run_id == AgateRun.id)
        .join(AgateGraph, AgateRun.graph_id == AgateGraph.id)
        .outerjoin(
            SubstrateArticle,
            col(AgateProcessedItem.substrate_article_id) == col(SubstrateArticle.id),
        )
        .where(AgateGraph.project_id == project_id)
    )


def _history_group_key(*, article_id: int | None, url: str | None) -> str | None:
    """Story key for an ungrouped history request. Saved article wins over URL."""
    if article_id is not None:
        return f"article:{int(article_id)}"
    if url is None:
        return None
    normalized = url.strip().lower()
    if not normalized:
        return None
    return f"url:{normalized}"


def _count_rows(session: Session, stmt: Any) -> int:
    count_stmt = select(func.count()).select_from(stmt.subquery())
    return int(session.exec(count_stmt).one())


def _select_row_fields(source: Any) -> Any:
    return select(*(source.c[name] for name in _ROW_FIELDS))


def _rows_from_results(
    rows: Any,
    *,
    fixed_processing_count: int | None = None,
) -> list[ProjectProcessedItemRow]:
    out: list[ProjectProcessedItemRow] = []
    for row in rows:
        mapping = row._mapping
        item_id = mapping["item_id"]
        run_id = mapping["run_id"]
        if item_id is None or not run_id:
            continue
        title, url = resolve_project_item_title_and_url(
            item_id=int(item_id),
            source_file=mapping["source_file"],
            input_json=mapping["input_json"],
            article_headline=mapping["article_headline"],
            article_url=mapping["article_url"],
        )
        if fixed_processing_count is None:
            processing_count = int(mapping["processing_count"])
        else:
            processing_count = fixed_processing_count
        resolved_article_id = mapping["resolved_article_id"]
        out.append(
            ProjectProcessedItemRow(
                id=int(item_id),
                run_id=str(run_id),
                flow_name=str(mapping["flow_name"] or ""),
                title=title,
                url=url,
                status=str(mapping["status"]),
                created_at=mapping["created_at"],
                source_file=mapping["source_file"],
                processing_count=processing_count,
                article_id=int(resolved_article_id) if resolved_article_id is not None else None,
            )
        )
    return out


def _list_story_history(
    session: Session,
    project_id: int,
    *,
    group_key: str,
    limit: int,
    offset: int,
) -> tuple[list[ProjectProcessedItemRow], int]:
    items = _project_items_select(session, project_id).subquery("history_items")
    stmt = _select_row_fields(items).where(items.c.group_key == group_key)
    total = _count_rows(session, stmt)
    page = (
        stmt.order_by(items.c.created_at.desc(), items.c.item_id.desc()).offset(offset).limit(limit)
    )
    rows = _rows_from_results(session.exec(page).all(), fixed_processing_count=1)
    return rows, total


def _list_grouped_stories(
    session: Session,
    project_id: int,
    *,
    query: str | None,
    limit: int,
    offset: int,
) -> tuple[list[ProjectProcessedItemRow], int]:
    items = _project_items_select(session, project_id).subquery("project_items")
    if query:
        matched = _apply_project_item_keyword_filter(
            _project_items_select(session, project_id),
            query,
            session,
        ).subquery("matched_items")
        qualifying = select(matched.c.group_key).distinct()
        scoped = (
            select(*(items.c[name] for name in (*_ROW_FIELDS, "group_key")))
            .where(items.c.group_key.in_(qualifying))
            .subquery("scoped_items")
        )
    else:
        scoped = items

    ranked = select(
        *(scoped.c[name] for name in _ROW_FIELDS),
        func.row_number()
        .over(
            partition_by=scoped.c.group_key,
            order_by=(scoped.c.created_at.desc(), scoped.c.item_id.desc()),
        )
        .label("rn"),
        func.count(scoped.c.item_id)
        .over(partition_by=scoped.c.group_key)
        .label("processing_count"),
    ).subquery("ranked_items")
    latest = (
        _select_row_fields(ranked).add_columns(ranked.c.processing_count).where(ranked.c.rn == 1)
    )
    total = _count_rows(session, latest)
    page = (
        latest.order_by(ranked.c.created_at.desc(), ranked.c.item_id.desc())
        .offset(offset)
        .limit(limit)
    )
    return _rows_from_results(session.exec(page).all()), total


def list_project_processed_items(
    session: Session,
    project_id: int,
    *,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    article_id: int | None = None,
    url: str | None = None,
) -> tuple[list[ProjectProcessedItemRow], int]:
    """Return one row per story, or every processing when a story key is set.

    Keyword search chooses which stories qualify. The row is still the newest
    processing in that story. ``article_id`` or ``url`` returns that story's
    processings newest first and ignores ``q``.
    """
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    query = (q or "").strip() or None
    group_key = _history_group_key(article_id=article_id, url=url)
    if group_key is not None:
        return _list_story_history(
            session,
            project_id,
            group_key=group_key,
            limit=limit,
            offset=offset,
        )
    return _list_grouped_stories(
        session,
        project_id,
        query=query,
        limit=limit,
        offset=offset,
    )
