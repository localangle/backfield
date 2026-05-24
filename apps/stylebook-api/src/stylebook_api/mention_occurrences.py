"""Replace substrate mention occurrences for one article+location (Review saves)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backfield_db import (
    SubstrateArticle,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from sqlmodel import Session, col, select


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _simple_find_span(
    haystack: str,
    needle: str,
    *,
    search_from: int = 0,
) -> tuple[int, int] | None:
    text = needle.strip()
    if not text or search_from < 0:
        return None
    idx = haystack.find(text, search_from)
    if idx < 0:
        return None
    return idx, idx + len(text)


def replace_mention_occurrences_for_article(
    session: Session,
    *,
    article_id: int,
    location_id: int,
    occurrences_in: list[dict[str, Any]],
) -> list[SubstrateLocationMentionOccurrence]:
    """Replace active user_review occurrences; preserve other source kinds until re-ingest."""
    mention = session.exec(
        select(SubstrateLocationMention).where(
            SubstrateLocationMention.article_id == article_id,
            SubstrateLocationMention.location_id == location_id,
            col(SubstrateLocationMention.deleted).is_(False),
        )
    ).first()
    if mention is None or mention.id is None:
        mention = SubstrateLocationMention(
            article_id=article_id,
            location_id=location_id,
            source_kind="user_review",
            edited=True,
        )
        session.add(mention)
        session.flush()

    article = session.get(SubstrateArticle, article_id)
    article_text = str(article.text) if article and article.text else ""

    now = _utcnow()
    existing = session.exec(
        select(SubstrateLocationMentionOccurrence).where(
            SubstrateLocationMentionOccurrence.location_mention_id == int(mention.id),
            SubstrateLocationMentionOccurrence.suppressed == False,  # noqa: E712
        )
    ).all()
    for row in existing:
        row.suppressed = True
        row.updated_at = now
        session.add(row)
    session.flush()

    search_from = 0
    created: list[SubstrateLocationMentionOccurrence] = []
    for order, raw in enumerate(occurrences_in):
        if not isinstance(raw, dict):
            continue
        if raw.get("suppressed"):
            continue
        text = raw.get("mention_text") or raw.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        mention_text = text.strip()
        start_raw = raw.get("start_char")
        end_raw = raw.get("end_char")
        start: int | None = int(start_raw) if isinstance(start_raw, int) else None
        end: int | None = int(end_raw) if isinstance(end_raw, int) else None
        if start is None or end is None:
            span = _simple_find_span(article_text, mention_text, search_from=search_from)
            if span is not None:
                start, end = span
                search_from = max(search_from, end)

        row = SubstrateLocationMentionOccurrence(
            location_mention_id=int(mention.id),
            source_kind="user_review",
            source_details_json={"source": "agate_review"},
            mention_text=mention_text,
            quote_text=raw.get("quote_text") if isinstance(raw.get("quote_text"), str) else None,
            start_char=start,
            end_char=end,
            occurrence_order=order,
            labels_json=[],
            suppressed=False,
        )
        session.add(row)
        created.append(row)
    session.flush()
    mention.edited = True
    mention.updated_at = now
    session.add(mention)
    session.flush()
    return created
