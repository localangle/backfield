"""Distinct filter values for public article search."""

from __future__ import annotations

from backfield_db import SubstrateArticle
from pydantic import BaseModel
from sqlmodel import Session, select

from backfield_entities.public.article_metadata import distinct_meta_categories


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
        format_categories=distinct_meta_categories(
            session,
            project_id=project_id,
            meta_type="format",
        ),
        topic_categories=distinct_meta_categories(
            session,
            project_id=project_id,
            meta_type="topic",
        ),
        subject_categories=distinct_meta_categories(
            session,
            project_id=project_id,
            meta_type="subject",
        ),
    )
