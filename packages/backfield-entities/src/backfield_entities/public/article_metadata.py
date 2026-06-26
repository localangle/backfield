"""Article metadata discovery for the public API."""

from __future__ import annotations

from backfield_db import SubstrateArticle, SubstrateArticleMeta
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from backfield_entities.public.article_scope import get_public_article_row
from backfield_entities.public.articles import PublicArticleMetaOut, _meta_rows_for_articles


class PublicArticleMetaTypesOut(BaseModel):
    meta_types: list[str] = Field(default_factory=list)


class PublicArticleMetaValuesOut(BaseModel):
    meta_type: str
    values: list[str] = Field(default_factory=list)


class PublicArticleMetadataOut(BaseModel):
    article_id: int
    meta_types: list[str] = Field(default_factory=list)
    metadata: list[PublicArticleMetaOut] = Field(default_factory=list)


def distinct_meta_categories(
    session: Session,
    *,
    project_id: int,
    meta_type: str,
) -> list[str]:
    """Return distinct non-empty category values for one metadata type in a project."""
    meta_type_value = meta_type.strip()
    if not meta_type_value:
        return []
    rows = session.exec(
        select(SubstrateArticleMeta.category)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateArticleMeta.article_id)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            SubstrateArticleMeta.meta_type == meta_type_value,
            SubstrateArticleMeta.category != "",
        )
        .distinct()
        .order_by(SubstrateArticleMeta.category)
    ).all()
    return [str(value).strip() for value in rows if str(value).strip()]


def list_public_article_meta_types(
    session: Session,
    *,
    project_id: int,
) -> PublicArticleMetaTypesOut:
    """Return distinct metadata types attached to articles in a project."""
    rows = session.exec(
        select(SubstrateArticleMeta.meta_type)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateArticleMeta.article_id)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            SubstrateArticleMeta.meta_type != "",
        )
        .distinct()
        .order_by(SubstrateArticleMeta.meta_type)
    ).all()
    meta_types = [str(value).strip() for value in rows if str(value).strip()]
    return PublicArticleMetaTypesOut(meta_types=meta_types)


def list_public_article_meta_values(
    session: Session,
    *,
    project_id: int,
    meta_type: str,
) -> PublicArticleMetaValuesOut:
    """Return distinct category values for one metadata type in a project."""
    meta_type_value = meta_type.strip()
    values = distinct_meta_categories(
        session,
        project_id=project_id,
        meta_type=meta_type_value,
    )
    return PublicArticleMetaValuesOut(meta_type=meta_type_value, values=values)


def get_public_article_metadata(
    session: Session,
    *,
    project_id: int,
    article_id: int,
) -> PublicArticleMetadataOut | None:
    """Return metadata rows and distinct types for one article, or None when missing."""
    article = get_public_article_row(
        session,
        project_id=project_id,
        article_id=article_id,
    )
    if article is None:
        return None
    metadata = _meta_rows_for_articles(session, [article_id]).get(article_id, [])
    meta_types = sorted({row.meta_type for row in metadata})
    return PublicArticleMetadataOut(
        article_id=article_id,
        meta_types=meta_types,
        metadata=metadata,
    )
