"""Article-level metadata tags linked to ``substrate_article``."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Text
from sqlmodel import Field, SQLModel, UniqueConstraint, func


class SubstrateArticleMeta(SQLModel, table=True):
    """One classified metadata tag per article and meta_type (Article Metadata → DBOutput)."""

    __tablename__ = "substrate_article_meta"
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "meta_type",
            "category",
            name="uq_substrate_article_meta_article_id_meta_type_category",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    article_id: int = Field(foreign_key="substrate_article.id", index=True)
    meta_type: str = Field(sa_column=Column(Text, nullable=False, index=True))
    category: str = Field(sa_column=Column(Text, nullable=False))
    rationale: str = Field(sa_column=Column(Text, nullable=False))
    confidence: float = Field(sa_column=Column(Float, nullable=False))
    prompt_preset: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    source_run_id: str | None = Field(
        default=None,
        foreign_key="agate_run.id",
        index=True,
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
