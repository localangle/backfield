"""Per-type semantic document tables (occurrence-level, pgvector-backed).

V1 creates concrete tables for entity types with durable mention occurrence rows today:
person, location, and organization. When work gains ``substrate_work_mention_occurrence``,
add a matching ``substrate_work_semantic_document`` model using the same column pattern.

Stylebook canonical ids are **not** stored on semantic rows; resolve them at query time via
``person_id`` / ``location_id`` / ``organization_id`` joins to substrate entity tables.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict
from sqlalchemy import Boolean, Column, DateTime, Index, Text, UniqueConstraint, func
from sqlmodel import Field, SQLModel

from backfield_db.pgvector import DEFAULT_SEMANTIC_EMBEDDING_DIMENSIONS, _PostgresVector
from backfield_db.semantic_indexing import (
    SEMANTIC_DOCUMENT_KIND_MENTION_OCCURRENCE,
    SEMANTIC_EMBEDDING_STATUS_PENDING,
)


class SubstratePersonSemanticDocument(SQLModel, table=True):
    """Semantic index row for one person mention occurrence."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    __tablename__ = "substrate_person_semantic_document"
    __table_args__ = (
        UniqueConstraint(
            "person_mention_occurrence_id",
            name="uq_substrate_person_sem_doc_occurrence",
        ),
        Index(
            "idx_substrate_person_sem_doc_project_article",
            "project_id",
            "article_id",
        ),
        Index(
            "idx_substrate_person_sem_doc_project_person",
            "project_id",
            "person_id",
        ),
        Index(
            "idx_substrate_person_sem_doc_project_status",
            "project_id",
            "embedding_status",
            "active",
        ),
        Index(
            "idx_substrate_person_sem_doc_project_active",
            "project_id",
            "active",
            "stale",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    article_id: int = Field(foreign_key="substrate_article.id", index=True)
    person_id: int = Field(foreign_key="substrate_person.id", index=True)
    person_mention_id: int = Field(foreign_key="substrate_person_mention.id", index=True)
    person_mention_occurrence_id: int = Field(
        foreign_key="substrate_person_mention_occurrence.id",
        index=True,
    )
    document_kind: str = Field(
        default=SEMANTIC_DOCUMENT_KIND_MENTION_OCCURRENCE,
        sa_column=Column(
            Text,
            nullable=False,
            server_default=SEMANTIC_DOCUMENT_KIND_MENTION_OCCURRENCE,
        ),
    )
    search_text: str = Field(sa_column=Column(Text, nullable=False))
    source_hash: str = Field(sa_column=Column(Text, nullable=False, index=True))
    active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
    )
    stale: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    embedding_status: str = Field(
        default=SEMANTIC_EMBEDDING_STATUS_PENDING,
        sa_column=Column(Text, nullable=False, server_default=SEMANTIC_EMBEDDING_STATUS_PENDING),
    )
    embedding_model: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    embedding_dimensions: int | None = Field(default=None)
    embedding_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    embedding: object | None = Field(
        default=None,
        sa_column=Column(_PostgresVector(DEFAULT_SEMANTIC_EMBEDDING_DIMENSIONS), nullable=True),
    )
    embedded_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class SubstrateOrganizationSemanticDocument(SQLModel, table=True):
    """Semantic index row for one organization mention occurrence."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    __tablename__ = "substrate_organization_semantic_document"
    __table_args__ = (
        UniqueConstraint(
            "organization_mention_occurrence_id",
            name="uq_substrate_organization_sem_doc_occurrence",
        ),
        Index(
            "idx_substrate_organization_sem_doc_project_article",
            "project_id",
            "article_id",
        ),
        Index(
            "idx_substrate_organization_sem_doc_project_organization",
            "project_id",
            "organization_id",
        ),
        Index(
            "idx_substrate_organization_sem_doc_project_status",
            "project_id",
            "embedding_status",
            "active",
        ),
        Index(
            "idx_substrate_organization_sem_doc_project_active",
            "project_id",
            "active",
            "stale",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    article_id: int = Field(foreign_key="substrate_article.id", index=True)
    organization_id: int = Field(foreign_key="substrate_organization.id", index=True)
    organization_mention_id: int = Field(
        foreign_key="substrate_organization_mention.id",
        index=True,
    )
    organization_mention_occurrence_id: int = Field(
        foreign_key="substrate_organization_mention_occurrence.id",
        index=True,
    )
    document_kind: str = Field(
        default=SEMANTIC_DOCUMENT_KIND_MENTION_OCCURRENCE,
        sa_column=Column(
            Text,
            nullable=False,
            server_default=SEMANTIC_DOCUMENT_KIND_MENTION_OCCURRENCE,
        ),
    )
    search_text: str = Field(sa_column=Column(Text, nullable=False))
    source_hash: str = Field(sa_column=Column(Text, nullable=False, index=True))
    active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
    )
    stale: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    embedding_status: str = Field(
        default=SEMANTIC_EMBEDDING_STATUS_PENDING,
        sa_column=Column(Text, nullable=False, server_default=SEMANTIC_EMBEDDING_STATUS_PENDING),
    )
    embedding_model: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    embedding_dimensions: int | None = Field(default=None)
    embedding_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    embedding: object | None = Field(
        default=None,
        sa_column=Column(_PostgresVector(DEFAULT_SEMANTIC_EMBEDDING_DIMENSIONS), nullable=True),
    )
    embedded_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class SubstrateLocationSemanticDocument(SQLModel, table=True):
    """Semantic index row for one location mention occurrence."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    __tablename__ = "substrate_location_semantic_document"
    __table_args__ = (
        UniqueConstraint(
            "location_mention_occurrence_id",
            name="uq_substrate_location_sem_doc_occurrence",
        ),
        Index(
            "idx_substrate_location_sem_doc_project_article",
            "project_id",
            "article_id",
        ),
        Index(
            "idx_substrate_location_sem_doc_project_location",
            "project_id",
            "location_id",
        ),
        Index(
            "idx_substrate_location_sem_doc_project_status",
            "project_id",
            "embedding_status",
            "active",
        ),
        Index(
            "idx_substrate_location_sem_doc_project_active",
            "project_id",
            "active",
            "stale",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    article_id: int = Field(foreign_key="substrate_article.id", index=True)
    location_id: int = Field(foreign_key="substrate_location.id", index=True)
    location_mention_id: int = Field(foreign_key="substrate_location_mention.id", index=True)
    location_mention_occurrence_id: int = Field(
        foreign_key="substrate_location_mention_occurrence.id",
        index=True,
    )
    document_kind: str = Field(
        default=SEMANTIC_DOCUMENT_KIND_MENTION_OCCURRENCE,
        sa_column=Column(
            Text,
            nullable=False,
            server_default=SEMANTIC_DOCUMENT_KIND_MENTION_OCCURRENCE,
        ),
    )
    search_text: str = Field(sa_column=Column(Text, nullable=False))
    source_hash: str = Field(sa_column=Column(Text, nullable=False, index=True))
    active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
    )
    stale: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    embedding_status: str = Field(
        default=SEMANTIC_EMBEDDING_STATUS_PENDING,
        sa_column=Column(Text, nullable=False, server_default=SEMANTIC_EMBEDDING_STATUS_PENDING),
    )
    embedding_model: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    embedding_dimensions: int | None = Field(default=None)
    embedding_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    embedding: object | None = Field(
        default=None,
        sa_column=Column(_PostgresVector(DEFAULT_SEMANTIC_EMBEDDING_DIMENSIONS), nullable=True),
    )
    embedded_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
