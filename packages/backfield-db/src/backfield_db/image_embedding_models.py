"""Image-level embedding rows linked to ``substrate_image``."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, SQLModel, UniqueConstraint, func

from backfield_db.pgvector import DEFAULT_SEMANTIC_EMBEDDING_DIMENSIONS, _PostgresVector


class SubstrateImageEmbedding(SQLModel, table=True):
    """One embedding vector per substrate image (EmbedImages → DBOutput persist)."""

    __tablename__ = "substrate_image_embedding"
    __table_args__ = (
        UniqueConstraint("substrate_image_id", name="uq_substrate_image_embedding_image_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    substrate_image_id: int = Field(foreign_key="substrate_image.id", index=True)
    generated_text: str = Field(sa_column=Column(Text, nullable=False))
    vision_model: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    vision_ai_model_config_id: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
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
