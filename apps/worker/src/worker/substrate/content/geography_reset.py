"""Replace all pipeline geography for one article before a flagged re-run persist."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db import SubstrateLocation, SubstrateLocationMention
from backfield_stylebook.substrate_canonical_link_actions import (
    dispose_orphan_substrate_without_requeue,
)
from sqlalchemy import func
from sqlmodel import Session, select


@dataclass(frozen=True)
class ArticleGeographyReplaceStats:
    mentions_cleared: int
    substrates_disposed: int


def replace_machine_geography_for_article(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    stylebook_id: int | None = None,
) -> ArticleGeographyReplaceStats:
    """Soft-delete all mentions for ``article_id``; dispose orphan substrates (no re-queue).

    Does not delete ``substrate_location`` rows still referenced by other articles.
    Fresh ingest in the same persist pass may recreate places for this story.
    """
    del stylebook_id  # unlink uses the canonical row's stylebook when disposing linked rows
    if article_id <= 0:
        return ArticleGeographyReplaceStats(mentions_cleared=0, substrates_disposed=0)

    mentions = list(
        session.exec(
            select(SubstrateLocationMention).where(
                SubstrateLocationMention.article_id == int(article_id),
            )
        ).all()
    )
    if not mentions:
        return ArticleGeographyReplaceStats(mentions_cleared=0, substrates_disposed=0)

    affected_location_ids: set[int] = set()
    cleared = 0
    for mention in mentions:
        if not bool(mention.deleted):
            cleared += 1
        mention.deleted = True
        session.add(mention)
        affected_location_ids.add(int(mention.location_id))
    session.flush()

    disposed = 0
    for lid in affected_location_ids:
        remaining = int(
            session.scalar(
                select(func.count())
                .select_from(SubstrateLocationMention)
                .where(
                    SubstrateLocationMention.location_id == int(lid),
                    SubstrateLocationMention.deleted == False,  # noqa: E712
                )
            )
            or 0
        )
        if remaining > 0:
            continue
        loc = session.get(SubstrateLocation, int(lid))
        if loc is None or int(loc.project_id) != int(project_id):
            continue
        dispose_orphan_substrate_without_requeue(
            session,
            location=loc,
            provenance="agate_rerun_geography_replace",
        )
        disposed += 1

    return ArticleGeographyReplaceStats(
        mentions_cleared=cleared,
        substrates_disposed=disposed,
    )
