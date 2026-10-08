"""Project-scoped processed-item list and headline/URL search for Agate UI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backfield_db import AgateGraph, AgateProcessedItem, AgateRun, SubstrateArticle
from backfield_entities.public.keyword_query import article_keyword_tsquery
from sqlalchemy import String, and_, case, cast, func, literal, or_, union_all
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


def _matching_article_ids(session: Session, project_id: int, query: str) -> Any:
    """Article ids whose headline or URL match. Postgres uses the headline/URL GIN index."""
    stmt = select(SubstrateArticle.id).where(SubstrateArticle.project_id == project_id)
    if session.get_bind().dialect.name == "postgresql":
        return stmt.where(_headline_url_tsvector().op("@@")(article_keyword_tsquery(query)))
    pattern = f"%{query.strip()}%"
    return stmt.where(
        or_(
            SubstrateArticle.headline.ilike(pattern),
            SubstrateArticle.url.ilike(pattern),
        )
    )


def _normalized_sql_url(url_expr: Any) -> Any:
    return func.nullif(func.lower(func.trim(url_expr)), "")


def _prefixed_key(prefix: str, value: Any) -> Any:
    return literal(prefix).op("||")(cast(value, String))


def _input_url_norm(dialect: str) -> Any:
    return _normalized_sql_url(
        _json_text_field(AgateProcessedItem.input_json, "url", dialect=dialect)
    )


def _article_url_map(project_id: int) -> Any:
    """One article id per normalized URL. Built once, then hash-joined."""
    url_norm = _normalized_sql_url(SubstrateArticle.url)
    return (
        select(
            func.min(SubstrateArticle.id).label("id"),
            url_norm.label("url_norm"),
        )
        .where(SubstrateArticle.project_id == project_id, url_norm.is_not(None))
        .group_by(url_norm)
        .subquery("article_url_map")
    )


def _join_project_items(stmt: Any, project_id: int) -> Any:
    return (
        stmt.join(AgateRun, AgateProcessedItem.run_id == AgateRun.id)
        .join(AgateGraph, AgateRun.graph_id == AgateGraph.id)
        .outerjoin(
            SubstrateArticle,
            col(AgateProcessedItem.substrate_article_id) == col(SubstrateArticle.id),
        )
        .where(AgateGraph.project_id == project_id)
    )


def _linked_item_keys(project_id: int) -> Any:
    """Linked processings. Grouped by saved article id, with no input JSON parse."""
    resolved_article_id = AgateProcessedItem.substrate_article_id
    group_key = _prefixed_key("article:", resolved_article_id)
    return _join_project_items(
        select(
            AgateProcessedItem.id.label("item_id"),
            AgateProcessedItem.created_at.label("created_at"),
            group_key.label("group_key"),
            resolved_article_id.label("resolved_article_id"),
        ).where(AgateProcessedItem.substrate_article_id.is_not(None)),
        project_id,
    )


def _unlinked_item_keys(session: Session, project_id: int) -> Any:
    """Unlinked processings. URL lookup is one grouped article map, not per item."""
    dialect = session.get_bind().dialect.name
    input_url_norm = _input_url_norm(dialect)
    url_map = _article_url_map(project_id)
    resolved_article_id = url_map.c.id
    group_key = case(
        (resolved_article_id.is_not(None), _prefixed_key("article:", resolved_article_id)),
        (input_url_norm.is_not(None), _prefixed_key("url:", input_url_norm)),
        else_=_prefixed_key("item:", AgateProcessedItem.id),
    )
    return _join_project_items(
        select(
            AgateProcessedItem.id.label("item_id"),
            AgateProcessedItem.created_at.label("created_at"),
            group_key.label("group_key"),
            resolved_article_id.label("resolved_article_id"),
        )
        .outerjoin(
            url_map,
            url_map.c.url_norm == input_url_norm,
        )
        .where(AgateProcessedItem.substrate_article_id.is_(None)),
        project_id,
    )


def _item_keys_union(session: Session, project_id: int) -> Any:
    return union_all(
        _linked_item_keys(project_id),
        _unlinked_item_keys(session, project_id),
    ).subquery("item_keys")


def _qualifying_group_keys(session: Session, project_id: int, query: str) -> Any:
    """Story keys where any processing matches headline, URL, or source file."""
    dialect = session.get_bind().dialect.name
    pattern = f"%{query.strip()}%"
    article_ids = _matching_article_ids(session, project_id, query)
    input_headline = _json_text_field(AgateProcessedItem.input_json, "headline", dialect=dialect)
    input_title = _json_text_field(AgateProcessedItem.input_json, "title", dialect=dialect)
    input_input_headline = _json_text_field(
        AgateProcessedItem.input_json, "input_headline", dialect=dialect
    )
    input_url = _json_text_field(AgateProcessedItem.input_json, "url", dialect=dialect)
    field_match = or_(
        AgateProcessedItem.source_file.ilike(pattern),
        input_headline.ilike(pattern),
        input_title.ilike(pattern),
        input_input_headline.ilike(pattern),
        input_url.ilike(pattern),
    )
    keys = _item_keys_union(session, project_id)
    matched_items = _join_project_items(
        select(AgateProcessedItem.id.label("item_id")).where(
            or_(AgateProcessedItem.substrate_article_id.in_(article_ids), field_match)
        ),
        project_id,
    ).subquery("matched_items")
    return (
        select(keys.c.group_key)
        .where(keys.c.item_id.in_(select(matched_items.c.item_id)))
        .distinct()
    )


def _keys_statement(session: Session, project_id: int, query: str | None) -> Any:
    keys = _item_keys_union(session, project_id)
    stmt = select(
        keys.c.item_id,
        keys.c.created_at,
        keys.c.group_key,
        keys.c.resolved_article_id,
    )
    if not query:
        return stmt
    return stmt.where(keys.c.group_key.in_(_qualifying_group_keys(session, project_id, query)))


def _keys_cte(session: Session, project_id: int, query: str | None) -> Any:
    """Story keys as a CTE. Postgres materializes them so count and page share one scan.

    ``cte(materialized=True)`` is not available in SQLAlchemy 2.0.49. A dialect
    prefix compiles to ``AS MATERIALIZED`` on Postgres and is omitted elsewhere.
    """
    stmt = _keys_statement(session, project_id, query)
    return stmt.cte("project_item_keys").prefix_with("MATERIALIZED", dialect="postgresql")


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


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _row_from_display(
    mapping: Any,
    *,
    processing_count: int,
    article_id: int | None,
) -> ProjectProcessedItemRow | None:
    item_id = mapping["item_id"]
    run_id = mapping["run_id"]
    if item_id is None or not run_id:
        return None
    title, url = resolve_project_item_title_and_url(
        item_id=int(item_id),
        source_file=mapping["source_file"],
        input_json=mapping["input_json"],
        article_headline=mapping["article_headline"],
        article_url=mapping["article_url"],
    )
    return ProjectProcessedItemRow(
        id=int(item_id),
        run_id=str(run_id),
        flow_name=str(mapping["flow_name"] or ""),
        title=title,
        url=url,
        status=str(mapping["status"]),
        created_at=mapping["created_at"],
        source_file=mapping["source_file"],
        processing_count=processing_count,
        article_id=article_id,
    )


def _display_select(project_id: int) -> Any:
    return _join_project_items(
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
        ),
        project_id,
    )


def _display_rows_for_ids(
    session: Session,
    project_id: int,
    winners: list[tuple[int, int, int | None]],
) -> list[ProjectProcessedItemRow]:
    """Load review fields for the already chosen story rows, in winner order."""
    if not winners:
        return []
    meta = {item_id: (count, article_id) for item_id, count, article_id in winners}
    stmt = _display_select(project_id).where(col(AgateProcessedItem.id).in_(list(meta)))
    by_id: dict[int, ProjectProcessedItemRow] = {}
    for row in session.exec(stmt).all():
        mapping = row._mapping
        item_id = int(mapping["item_id"])
        count, article_id = meta[item_id]
        built = _row_from_display(mapping, processing_count=count, article_id=article_id)
        if built is not None:
            by_id[item_id] = built
    return [by_id[item_id] for item_id, _count, _article_id in winners if item_id in by_id]


def _history_select(
    session: Session,
    project_id: int,
    *,
    article_id: int | None,
    url: str | None,
) -> Any:
    dialect = session.get_bind().dialect.name
    input_url_norm = _input_url_norm(dialect)
    display = _display_select(project_id)
    if article_id is not None:
        url_map = _article_url_map(project_id)
        linked = display.where(AgateProcessedItem.substrate_article_id == article_id)
        unlinked = _join_project_items(
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
            ).join(
                url_map,
                and_(
                    AgateProcessedItem.substrate_article_id.is_(None),
                    url_map.c.url_norm == input_url_norm,
                    url_map.c.id == article_id,
                ),
            ),
            project_id,
        )
        return union_all(linked, unlinked)
    normalized = (url or "").strip().lower()
    return display.where(
        AgateProcessedItem.substrate_article_id.is_(None),
        input_url_norm == normalized,
    )


_DISPLAY_COLUMNS = (
    "item_id",
    "run_id",
    "flow_name",
    "status",
    "created_at",
    "source_file",
    "input_json",
    "article_headline",
    "article_url",
)


def _list_story_history(
    session: Session,
    project_id: int,
    *,
    article_id: int | None,
    url: str | None,
    limit: int,
    offset: int,
) -> tuple[list[ProjectProcessedItemRow], int]:
    history = _history_select(session, project_id, article_id=article_id, url=url).subquery(
        "history_rows"
    )
    total = int(session.exec(select(func.count()).select_from(history)).one())
    page = session.exec(
        select(*(history.c[name] for name in _DISPLAY_COLUMNS))
        .order_by(history.c.created_at.desc(), history.c.item_id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    rows: list[ProjectProcessedItemRow] = []
    for row in page:
        built = _row_from_display(
            row._mapping,
            processing_count=1,
            article_id=article_id,
        )
        if built is not None:
            rows.append(built)
    return rows, total


def _list_grouped_stories(
    session: Session,
    project_id: int,
    *,
    query: str | None,
    limit: int,
    offset: int,
) -> tuple[list[ProjectProcessedItemRow], int]:
    """Aggregate story keys, count those groups, then load one page of winners.

    The count is ``count(*)`` of the grouped keys. It does not rank full item
    payloads or look up an article once per processed item.
    """
    keys = _keys_cte(session, project_id, query)
    grouped = (
        select(
            keys.c.group_key.label("group_key"),
            func.count(keys.c.item_id).label("processing_count"),
            func.max(keys.c.created_at).label("latest_at"),
        )
        .group_by(keys.c.group_key)
        .cte("story_groups")
    )
    total = int(session.exec(select(func.count()).select_from(grouped)).one())
    if total == 0 or offset >= total:
        return [], total

    page_groups = (
        select(
            grouped.c.group_key.label("group_key"),
            grouped.c.processing_count.label("processing_count"),
            grouped.c.latest_at.label("latest_at"),
        )
        .order_by(grouped.c.latest_at.desc(), grouped.c.group_key.desc())
        .offset(offset)
        .limit(limit)
        .subquery("page_groups")
    )
    winner_id = func.max(keys.c.item_id).label("item_id")
    winner_rows = session.exec(
        select(
            winner_id,
            page_groups.c.processing_count,
            func.max(keys.c.resolved_article_id).label("resolved_article_id"),
        )
        .select_from(keys)
        .join(
            page_groups,
            and_(
                keys.c.group_key == page_groups.c.group_key,
                keys.c.created_at == page_groups.c.latest_at,
            ),
        )
        .group_by(
            page_groups.c.group_key,
            page_groups.c.processing_count,
            page_groups.c.latest_at,
        )
        .order_by(page_groups.c.latest_at.desc(), winner_id.desc())
    ).all()
    winners = [
        (int(row.item_id), int(row.processing_count), _optional_int(row.resolved_article_id))
        for row in winner_rows
    ]
    return _display_rows_for_ids(session, project_id, winners), total


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
    if _history_group_key(article_id=article_id, url=url) is not None:
        return _list_story_history(
            session,
            project_id,
            article_id=article_id,
            url=url,
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
