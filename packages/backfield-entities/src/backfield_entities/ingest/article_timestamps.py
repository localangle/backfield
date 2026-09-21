"""Parse and backfill optional article ``published`` / ``updated`` timestamps."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backfield_db import AgateProcessedItem, BackfieldProject, SubstrateArticle
from sqlmodel import Session, col, select


def parse_article_timestamp(value: Any) -> datetime | None:
    """Parse an optional instant. Naive values are UTC; date-only values are not timestamps."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, str):
        raw = value.strip()
        if not raw or ("T" not in raw and " " not in raw):
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def _timestamp_candidates_from_payload(payload: object) -> list[dict[str, Any]]:
    """Prefer consolidated / DBOutput shapes, then S3 input, then the payload itself."""
    if not isinstance(payload, dict):
        return []
    candidates: list[dict[str, Any]] = []
    json_output = payload.get("json_output")
    if isinstance(json_output, dict):
        consolidated = json_output.get("consolidated")
        if isinstance(consolidated, dict):
            candidates.append(consolidated)
    consolidated = payload.get("consolidated")
    if isinstance(consolidated, dict):
        candidates.append(consolidated)
    stylebook_output = payload.get("stylebook_output")
    if isinstance(stylebook_output, dict):
        candidates.append(stylebook_output)
    s3_input = payload.get("s3_input")
    if isinstance(s3_input, dict):
        candidates.append(s3_input)
    candidates.append(payload)
    return candidates


def published_and_updated_raw_from_payload(
    payload: object,
) -> tuple[Any | None, Any | None]:
    """Return the first non-empty ``published`` / ``updated`` values from preferred blocks."""
    published: Any | None = None
    updated: Any | None = None
    for block in _timestamp_candidates_from_payload(payload):
        if published is None and "published" in block and block.get("published") not in (None, ""):
            published = block.get("published")
        if updated is None and "updated" in block and block.get("updated") not in (None, ""):
            updated = block.get("updated")
        if published is not None and updated is not None:
            break
    return published, updated


def published_and_updated_from_json(raw: str | None) -> tuple[datetime | None, datetime | None]:
    if not raw or not str(raw).strip():
        return None, None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, None
    published_raw, updated_raw = published_and_updated_raw_from_payload(payload)
    return parse_article_timestamp(published_raw), parse_article_timestamp(updated_raw)


def published_and_updated_from_processed_item(
    item: AgateProcessedItem,
) -> tuple[datetime | None, datetime | None]:
    """Prefer reviewed export JSON, then graph result, then input JSON."""
    published: datetime | None = None
    updated: datetime | None = None
    for raw in (item.reviewed_output_json, item.result_json, item.input_json):
        found_published, found_updated = published_and_updated_from_json(raw)
        if published is None:
            published = found_published
        if updated is None:
            updated = found_updated
        if published is not None and updated is not None:
            break
    return published, updated


def _processed_item_for_article(
    session: Session,
    article: SubstrateArticle,
) -> AgateProcessedItem | None:
    if article.source_item_id is not None:
        item = session.get(AgateProcessedItem, article.source_item_id)
        if item is not None:
            return item
    article_id = int(article.id) if article.id is not None else None
    if article_id is not None:
        linked = session.exec(
            select(AgateProcessedItem)
            .where(col(AgateProcessedItem.substrate_article_id) == article_id)
            .order_by(col(AgateProcessedItem.id).desc())
        ).first()
        if linked is not None:
            return linked
    ledger_id = (article.external_id or "").strip()
    if not ledger_id:
        return None
    return session.exec(
        select(AgateProcessedItem)
        .where(col(AgateProcessedItem.ingestion_ledger_id) == ledger_id)
        .order_by(col(AgateProcessedItem.id).desc())
    ).first()


@dataclass
class ArticleTimestampBackfillReport:
    scanned: int = 0
    published_filled: int = 0
    updated_filled: int = 0
    unchanged: int = 0
    missing_source: int = 0
    article_ids_published: list[int] = field(default_factory=list)
    article_ids_updated: list[int] = field(default_factory=list)
    missing_source_ids: list[int] = field(default_factory=list)


def backfill_article_timestamps(
    session: Session,
    *,
    apply: bool = False,
    project_id: int | None = None,
    project_slug: str | None = None,
    limit: int | None = None,
) -> ArticleTimestampBackfillReport:
    """Fill null ``published`` / ``updated`` from linked processed-item JSON.

    Never invents one timestamp from another, and never overwrites a non-null column.
    """
    report = ArticleTimestampBackfillReport()
    stmt = select(SubstrateArticle).where(
        col(SubstrateArticle.deleted) == False,  # noqa: E712
        (
            col(SubstrateArticle.published).is_(None)
            | col(SubstrateArticle.updated).is_(None)
        ),
    )
    slug = (project_slug or "").strip()
    if project_id is not None and slug:
        raise ValueError("Pass only one of project_id or project_slug.")
    if project_id is not None:
        stmt = stmt.where(col(SubstrateArticle.project_id) == project_id)
    elif slug:
        projects = list(session.exec(select(BackfieldProject).where(BackfieldProject.slug == slug)))
        if not projects:
            raise ValueError(f"No project found for slug {slug!r}.")
        if len(projects) > 1:
            raise ValueError(
                f"Slug {slug!r} matches {len(projects)} projects; pass --project-id instead."
            )
        stmt = stmt.where(col(SubstrateArticle.project_id) == int(projects[0].id))  # type: ignore[arg-type]
    stmt = stmt.order_by(col(SubstrateArticle.id).asc())
    if limit is not None:
        stmt = stmt.limit(limit)
    articles = list(session.exec(stmt).all())
    report.scanned = len(articles)

    for article in articles:
        article_id = int(article.id)  # type: ignore[arg-type]
        need_published = article.published is None
        need_updated = article.updated is None
        item = _processed_item_for_article(session, article)
        if item is None:
            report.missing_source += 1
            report.missing_source_ids.append(article_id)
            continue
        published, updated = published_and_updated_from_processed_item(item)
        changed = False
        if need_published and published is not None:
            report.published_filled += 1
            report.article_ids_published.append(article_id)
            if apply:
                article.published = published
            changed = True
        if need_updated and updated is not None:
            report.updated_filled += 1
            report.article_ids_updated.append(article_id)
            if apply:
                article.updated = updated
            changed = True
        if changed:
            if apply:
                session.add(article)
        else:
            report.unchanged += 1

    if apply:
        session.commit()
    return report
