"""Article-level embedding row linked to ``substrate_article``."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, SQLModel, UniqueConstraint, func

from backfield_db.pgvector import DEFAULT_SEMANTIC_EMBEDDING_DIMENSIONS, _PostgresVector


class SubstrateArticleEmbedding(SQLModel, table=True):
    """One embedding vector per article (EmbedText → DBOutput persist)."""

    __tablename__ = "substrate_article_embedding"
    __table_args__ = (
        UniqueConstraint("article_id", name="uq_substrate_article_embedding_article_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    article_id: int = Field(foreign_key="substrate_article.id", index=True)
    embedded_text: str = Field(sa_column=Column(Text, nullable=False))
    embedding_model: str = Field(sa_column=Column(Text, nullable=False, index=True))
    embedding_dimensions: int
    embedding_ai_model_config_id: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    embedding: object | None = Field(
        default=None,
        sa_column=Column(_PostgresVector(DEFAULT_SEMANTIC_EMBEDDING_DIMENSIONS), nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
