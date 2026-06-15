"""Distinct filter values for public article search."""

from __future__ import annotations

from backfield_db import SubstrateArticle, SubstrateArticleMeta
from pydantic import BaseModel
from sqlmodel import Session, select


class PublicArticleFacetsOut(BaseModel):
    authors: list[str]
    external_sources: list[str]
    format_categories: list[str]
    topic_categories: list[str]
    subject_categories: list[str]


def _distinct_article_field(
    session: Session,
    *,
    project_id: int,
    column,
) -> list[str]:
    rows = session.exec(
        select(column)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            column.isnot(None),
            column != "",
        )
        .distinct()
        .order_by(column)
    ).all()
    return [str(value).strip() for value in rows if str(value).strip()]


def _distinct_meta_categories(
    session: Session,
    *,
    project_id: int,
    meta_type: str,
) -> list[str]:
    rows = session.exec(
        select(SubstrateArticleMeta.category)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateArticleMeta.article_id)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            SubstrateArticleMeta.meta_type == meta_type,
            SubstrateArticleMeta.category != "",
        )
        .distinct()
        .order_by(SubstrateArticleMeta.category)
    ).all()
    return [str(value).strip() for value in rows if str(value).strip()]


def get_public_article_facets(session: Session, *, project_id: int) -> PublicArticleFacetsOut:
    """Return distinct authors, sources, and metadata categories for filter dropdowns."""
    return PublicArticleFacetsOut(
        authors=_distinct_article_field(
            session,
            project_id=project_id,
            column=SubstrateArticle.author,
        ),
        external_sources=_distinct_article_field(
            session,
            project_id=project_id,
            column=SubstrateArticle.external_source,
        ),
        format_categories=_distinct_meta_categories(
            session,
            project_id=project_id,
            meta_type="format",
        ),
        topic_categories=_distinct_meta_categories(
            session,
            project_id=project_id,
            meta_type="topic",
        ),
        subject_categories=_distinct_meta_categories(
            session,
            project_id=project_id,
            meta_type="subject",
        ),
    )
