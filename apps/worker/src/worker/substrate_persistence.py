"""Persist successful Agate graph outputs into shared substrate_* tables."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from worker.substrate_article import _sync_images, _upsert_article
from worker.substrate_location import _iter_place_entries, _upsert_location
from worker.substrate_mentions import _upsert_mention_and_occurrence
from worker.substrate_span import _find_mention_span

__all__ = ["persist_from_consolidated", "_find_mention_span"]


def persist_from_consolidated(
    session: Session,
    *,
    project_id: int,
    graph_id: str,
    run_id: str,
    consolidated: dict[str, Any],
) -> int:
    places = consolidated.get("places")
    if not isinstance(places, dict):
        raise RuntimeError(
            "DBOutput persistence requires consolidated['places'] (GeocodeAgent output)"
        )

    article = _upsert_article(
        session,
        project_id=project_id,
        consolidated=consolidated,
        run_id=run_id,
    )
    _sync_images(session, article_id=int(article.id), consolidated=consolidated)

    article_text = str(consolidated.get("text") or "")
    order = 0
    for bucket, entry in _iter_place_entries(places):
        loc = _upsert_location(
            session,
            project_id=project_id,
            bucket=bucket,
            entry=entry,
            run_id=run_id,
            graph_id=graph_id,
        )
        if loc is None or article.id is None:
            continue
        _upsert_mention_and_occurrence(
            session,
            article_id=int(article.id),
            location_id=int(loc.id),
            article_text=article_text,
            entry=entry,
            run_id=run_id,
            graph_id=graph_id,
            bucket=bucket,
            occurrence_order=order,
        )
        order += 1

    return int(article.id)
