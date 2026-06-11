"""Custom extracted record rows linked to ``substrate_article``."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Float, Integer, Text
from sqlmodel import Field, SQLModel, UniqueConstraint, func


class SubstrateCustomRecord(SQLModel, table=True):
    """One extracted record per article, record type, and position (Custom Extract → DBOutput)."""

    __tablename__ = "substrate_custom_record"
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "record_type",
            "record_index",
            name="uq_substrate_custom_record_article_type_index",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    article_id: int = Field(foreign_key="substrate_article.id", index=True)
    record_type: str = Field(sa_column=Column(Text, nullable=False, index=True))
    record_index: int = Field(sa_column=Column(Integer, nullable=False))
    fields_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    mentions_json: list[dict[str, Any]] = Field(sa_column=Column(JSON, nullable=False))
    # Snapshot of the declared field schema so historical rows render after node edits.
    field_schema_json: list[dict[str, Any]] = Field(sa_column=Column(JSON, nullable=False))
    confidence: float | None = Field(default=None, sa_column=Column(Float, nullable=True))
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
