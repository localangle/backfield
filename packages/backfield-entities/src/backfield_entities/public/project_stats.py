"""Project-level summary counts for the public API."""

from __future__ import annotations

from backfield_db import (
    SubstrateArticle,
    SubstrateArticleEmbedding,
    SubstrateImage,
    SubstrateImageEmbedding,
    SubstrateLocationMention,
    SubstrateLocationSemanticDocument,
    SubstrateOrganizationMention,
    SubstrateOrganizationSemanticDocument,
    SubstratePersonMention,
    SubstratePersonSemanticDocument,
)
from backfield_db.semantic_indexing import SEMANTIC_EMBEDDING_STATUS_READY
from pydantic import BaseModel
from sqlalchemy import func, union_all
from sqlmodel import Session, col, select


class PublicProjectCountStatsOut(BaseModel):
    """Total rows and the subset with semantic embeddings."""

    total: int
    embedded: int


class PublicProjectSummaryStatsOut(BaseModel):
    articles: PublicProjectCountStatsOut
    mentions: PublicProjectCountStatsOut
    images: PublicProjectCountStatsOut


def _count_public_mentions(
    session: Session,
    *,
    project_id: int,
    mention_model: type,
) -> int:
    value = session.exec(
        select(func.count())
        .select_from(mention_model)
        .join(SubstrateArticle, SubstrateArticle.id == mention_model.article_id)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            mention_model.deleted == False,  # noqa: E712
        )
    ).one()
    return int(value or 0)


def _embedded_mention_id_subquery(
    *,
    project_id: int,
    doc_model: type,
    mention_id_col,
    mention_model: type,
):
    return (
        select(mention_id_col.label("mention_id"))
        .select_from(doc_model)
        .join(mention_model, mention_model.id == mention_id_col)
        .join(SubstrateArticle, SubstrateArticle.id == mention_model.article_id)
        .where(
            doc_model.project_id == project_id,
            doc_model.active.is_(True),
            doc_model.stale.is_(False),
            doc_model.embedding_status == SEMANTIC_EMBEDDING_STATUS_READY,
            col(doc_model.embedding).isnot(None),
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            mention_model.deleted == False,  # noqa: E712
        )
    )


def _count_embedded_public_mentions(session: Session, *, project_id: int) -> int:
    """Distinct mentions with a ready semantic-document embedding (searchable)."""
    mention_id_queries = [
        _embedded_mention_id_subquery(
            project_id=project_id,
            doc_model=SubstratePersonSemanticDocument,
            mention_id_col=SubstratePersonSemanticDocument.person_mention_id,
            mention_model=SubstratePersonMention,
        ),
        _embedded_mention_id_subquery(
            project_id=project_id,
            doc_model=SubstrateLocationSemanticDocument,
            mention_id_col=SubstrateLocationSemanticDocument.location_mention_id,
            mention_model=SubstrateLocationMention,
        ),
        _embedded_mention_id_subquery(
            project_id=project_id,
            doc_model=SubstrateOrganizationSemanticDocument,
            mention_id_col=SubstrateOrganizationSemanticDocument.organization_mention_id,
            mention_model=SubstrateOrganizationMention,
        ),
    ]
    union_stmt = union_all(*mention_id_queries).subquery()
    value = session.exec(
        select(func.count(func.distinct(union_stmt.c.mention_id))).select_from(union_stmt)
    ).one()
    return int(value or 0)


def _count_articles(session: Session, *, project_id: int) -> int:
    value = session.exec(
        select(func.count())
        .select_from(SubstrateArticle)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
        )
    ).one()
    return int(value or 0)


def _count_embedded_articles(session: Session, *, project_id: int) -> int:
    value = session.exec(
        select(func.count())
        .select_from(SubstrateArticleEmbedding)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateArticleEmbedding.article_id)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            col(SubstrateArticleEmbedding.embedding).isnot(None),
        )
    ).one()
    return int(value or 0)


def _count_images(session: Session, *, project_id: int) -> int:
    value = session.exec(
        select(func.count())
        .select_from(SubstrateImage)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateImage.article_id)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
        )
    ).one()
    return int(value or 0)


def _count_embedded_images(session: Session, *, project_id: int) -> int:
    value = session.exec(
        select(func.count())
        .select_from(SubstrateImageEmbedding)
        .join(SubstrateImage, SubstrateImage.id == SubstrateImageEmbedding.substrate_image_id)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateImage.article_id)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            col(SubstrateImageEmbedding.embedding).isnot(None),
        )
    ).one()
    return int(value or 0)


def get_public_project_summary_stats(
    session: Session,
    *,
    project_id: int,
) -> PublicProjectSummaryStatsOut:
    """Return substrate summary counts scoped to non-deleted public articles."""
    mention_total = sum(
        _count_public_mentions(session, project_id=project_id, mention_model=model)
        for model in (
            SubstrateLocationMention,
            SubstratePersonMention,
            SubstrateOrganizationMention,
        )
    )
    return PublicProjectSummaryStatsOut(
        articles=PublicProjectCountStatsOut(
            total=_count_articles(session, project_id=project_id),
            embedded=_count_embedded_articles(session, project_id=project_id),
        ),
        mentions=PublicProjectCountStatsOut(
            total=mention_total,
            embedded=_count_embedded_public_mentions(session, project_id=project_id),
        ),
        images=PublicProjectCountStatsOut(
            total=_count_images(session, project_id=project_id),
            embedded=_count_embedded_images(session, project_id=project_id),
        ),
    )
