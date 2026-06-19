"""Project-scoped article lookup for public API routes."""

from __future__ import annotations

from backfield_db import SubstrateArticle
from sqlmodel import Session, select


def get_public_article_row(
    session: Session,
    *,
    project_id: int,
    article_id: int,
) -> SubstrateArticle | None:
    """Return a non-deleted article row when it belongs to ``project_id``."""
    return session.exec(
        select(SubstrateArticle).where(
            SubstrateArticle.id == article_id,
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
        )
    ).first()
