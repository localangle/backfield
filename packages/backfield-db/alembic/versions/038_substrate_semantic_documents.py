"""Pgvector extension and per-type semantic document tables (person, location).

Organization/work tables follow the same pattern once substrate occurrence tables exist.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "038_substrate_semantic_docs"
down_revision: Union[str, None] = "037_person_sort_key"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def _embedding_column():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from pgvector.sqlalchemy import Vector

        return sa.Column("embedding", Vector(1536), nullable=True)
    return sa.Column("embedding", sa.Text(), nullable=True)


def _create_person_semantic_document_table() -> None:
    op.create_table(
        "substrate_person_semantic_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("person_mention_id", sa.Integer(), nullable=False),
        sa.Column("person_mention_occurrence_id", sa.Integer(), nullable=False),
        sa.Column(
            "document_kind",
            sa.Text(),
            nullable=False,
            server_default="mention_occurrence",
        ),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "embedding_status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("embedding_error", sa.Text(), nullable=True),
        _embedding_column(),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="substrate_person_sem_doc_project_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["substrate_article.id"],
            name="substrate_person_sem_doc_article_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["substrate_person.id"],
            name="substrate_person_sem_doc_person_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["person_mention_id"],
            ["substrate_person_mention.id"],
            name="substrate_person_sem_doc_mention_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["person_mention_occurrence_id"],
            ["substrate_person_mention_occurrence.id"],
            name="substrate_person_sem_doc_occurrence_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="substrate_person_semantic_document_pkey"),
        sa.UniqueConstraint(
            "person_mention_occurrence_id",
            name="uq_substrate_person_sem_doc_occurrence",
        ),
    )
    op.create_index(
        "ix_substrate_person_sem_doc_project_id",
        "substrate_person_semantic_document",
        ["project_id"],
    )
    op.create_index(
        "ix_substrate_person_sem_doc_article_id",
        "substrate_person_semantic_document",
        ["article_id"],
    )
    op.create_index(
        "ix_substrate_person_sem_doc_person_id",
        "substrate_person_semantic_document",
        ["person_id"],
    )
    op.create_index(
        "ix_substrate_person_sem_doc_person_mention_id",
        "substrate_person_semantic_document",
        ["person_mention_id"],
    )
    op.create_index(
        "ix_substrate_person_sem_doc_person_mention_occurrence_id",
        "substrate_person_semantic_document",
        ["person_mention_occurrence_id"],
    )
    op.create_index(
        "ix_substrate_person_sem_doc_source_hash",
        "substrate_person_semantic_document",
        ["source_hash"],
    )
    op.create_index(
        "idx_substrate_person_sem_doc_project_article",
        "substrate_person_semantic_document",
        ["project_id", "article_id"],
    )
    op.create_index(
        "idx_substrate_person_sem_doc_project_person",
        "substrate_person_semantic_document",
        ["project_id", "person_id"],
    )
    op.create_index(
        "idx_substrate_person_sem_doc_project_status",
        "substrate_person_semantic_document",
        ["project_id", "embedding_status", "active"],
    )
    op.create_index(
        "idx_substrate_person_sem_doc_project_active",
        "substrate_person_semantic_document",
        ["project_id", "active", "stale"],
    )


def _create_location_semantic_document_table() -> None:
    op.create_table(
        "substrate_location_semantic_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("location_mention_id", sa.Integer(), nullable=False),
        sa.Column("location_mention_occurrence_id", sa.Integer(), nullable=False),
        sa.Column(
            "document_kind",
            sa.Text(),
            nullable=False,
            server_default="mention_occurrence",
        ),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "embedding_status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("embedding_error", sa.Text(), nullable=True),
        _embedding_column(),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="substrate_location_sem_doc_project_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["substrate_article.id"],
            name="substrate_location_sem_doc_article_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["substrate_location.id"],
            name="substrate_location_sem_doc_location_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["location_mention_id"],
            ["substrate_location_mention.id"],
            name="substrate_location_sem_doc_mention_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["location_mention_occurrence_id"],
            ["substrate_location_mention_occurrence.id"],
            name="substrate_location_sem_doc_occurrence_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="substrate_location_semantic_document_pkey"),
        sa.UniqueConstraint(
            "location_mention_occurrence_id",
            name="uq_substrate_location_sem_doc_occurrence",
        ),
    )
    op.create_index(
        "ix_substrate_location_sem_doc_project_id",
        "substrate_location_semantic_document",
        ["project_id"],
    )
    op.create_index(
        "ix_substrate_location_sem_doc_article_id",
        "substrate_location_semantic_document",
        ["article_id"],
    )
    op.create_index(
        "ix_substrate_location_sem_doc_location_id",
        "substrate_location_semantic_document",
        ["location_id"],
    )
    op.create_index(
        "ix_substrate_location_sem_doc_location_mention_id",
        "substrate_location_semantic_document",
        ["location_mention_id"],
    )
    op.create_index(
        "ix_substrate_location_sem_doc_location_mention_occurrence_id",
        "substrate_location_semantic_document",
        ["location_mention_occurrence_id"],
    )
    op.create_index(
        "ix_substrate_location_sem_doc_source_hash",
        "substrate_location_semantic_document",
        ["source_hash"],
    )
    op.create_index(
        "idx_substrate_location_sem_doc_project_article",
        "substrate_location_semantic_document",
        ["project_id", "article_id"],
    )
    op.create_index(
        "idx_substrate_location_sem_doc_project_location",
        "substrate_location_semantic_document",
        ["project_id", "location_id"],
    )
    op.create_index(
        "idx_substrate_location_sem_doc_project_status",
        "substrate_location_semantic_document",
        ["project_id", "embedding_status", "active"],
    )
    op.create_index(
        "idx_substrate_location_sem_doc_project_active",
        "substrate_location_semantic_document",
        ["project_id", "active", "stale"],
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    _create_person_semantic_document_table()
    _create_location_semantic_document_table()


def downgrade() -> None:
    op.drop_table("substrate_location_semantic_document")
    op.drop_table("substrate_person_semantic_document")
    # Do not DROP EXTENSION vector; other objects may depend on it in shared DBs.
