"""Organization entity schema: Stylebook canonical trio + substrate trio + semantic docs.

Revision id must fit ``alembic_version.version_num`` (varchar(32)).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "039_organization_schema"
down_revision: Union[str, None] = "038_substrate_semantic_docs"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def _embedding_column():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from pgvector.sqlalchemy import Vector

        return sa.Column("embedding", Vector(1536), nullable=True)
    return sa.Column("embedding", sa.Text(), nullable=True)


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "stylebook_organization_canonical",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("organization_type", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
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
            ["stylebook_id"],
            ["stylebook.id"],
            name="stylebook_organization_canonical_stylebook_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_organization_canonical_pkey"),
        sa.UniqueConstraint(
            "stylebook_id",
            "slug",
            name="uq_stylebook_organization_canonical_stylebook_slug",
        ),
    )
    op.create_index(
        "ix_stylebook_organization_canonical_stylebook_id",
        "stylebook_organization_canonical",
        ["stylebook_id"],
    )
    op.create_index(
        "ix_stylebook_organization_canonical_stylebook_type",
        "stylebook_organization_canonical",
        ["stylebook_id", "organization_type"],
    )

    op.create_table(
        "substrate_organization",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("organization_type", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'provisional'"),
        ),
        sa.Column("stylebook_organization_canonical_id", sa.Text(), nullable=True),
        sa.Column(
            "canonical_link_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unlinked'"),
        ),
        sa.Column("canonical_review_reasons_json", sa.JSON(), nullable=True),
        sa.Column("external_source", sa.Text(), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("identity_fingerprint", sa.Text(), nullable=True),
        sa.Column(
            "source_kind",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("source_details_json", sa.JSON(), nullable=True),
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
            name="substrate_organization_project_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_organization_canonical_id"],
            ["stylebook_organization_canonical.id"],
            name="substrate_organization_stylebook_organization_canonical_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="substrate_organization_pkey"),
        sa.UniqueConstraint(
            "project_id",
            "external_source",
            "external_id",
            name="uq_substrate_organization_project_external",
        ),
        sa.UniqueConstraint(
            "project_id",
            "identity_fingerprint",
            name="uq_substrate_organization_project_fingerprint",
        ),
    )
    op.create_index("ix_substrate_organization_project_id", "substrate_organization", ["project_id"])
    op.create_index(
        "ix_substrate_organization_normalized_name",
        "substrate_organization",
        ["normalized_name"],
    )
    op.create_index(
        "idx_substrate_organization_project_status",
        "substrate_organization",
        ["project_id", "status"],
    )
    op.create_index(
        "idx_substrate_organization_project_name",
        "substrate_organization",
        ["project_id", "normalized_name"],
    )
    op.create_index(
        "idx_substrate_organization_project_type",
        "substrate_organization",
        ["project_id", "organization_type"],
    )
    op.create_index(
        "ix_substrate_organization_stylebook_organization_canonical_id",
        "substrate_organization",
        ["stylebook_organization_canonical_id"],
    )
    op.create_index(
        "ix_substrate_organization_project_canonical",
        "substrate_organization",
        ["project_id", "stylebook_organization_canonical_id"],
    )
    op.create_index(
        "ix_substrate_organization_project_link_status",
        "substrate_organization",
        ["project_id", "canonical_link_status"],
    )
    if bind.dialect.name == "postgresql":
        op.create_index(
            "ix_substrate_organization_project_pending_queue",
            "substrate_organization",
            ["project_id"],
            postgresql_where=sa.text(
                "canonical_link_status = 'pending' AND stylebook_organization_canonical_id IS NULL"
            ),
        )

    op.add_column(
        "stylebook_organization_canonical",
        sa.Column("primary_substrate_organization_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "stylebook_organization_canonical_primary_substrate_organization_id_fkey",
        "stylebook_organization_canonical",
        "substrate_organization",
        ["primary_substrate_organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_stylebook_organization_canonical_primary_substrate_organization_id",
        "stylebook_organization_canonical",
        ["primary_substrate_organization_id"],
    )

    op.create_table(
        "substrate_organization_mention",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("role_in_story", sa.Text(), nullable=True),
        sa.Column("nature", sa.Text(), nullable=True),
        sa.Column(
            "nature_secondary_tags_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("review_data_json", sa.JSON(), nullable=True),
        sa.Column("added", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("edited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "source_kind",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("source_details_json", sa.JSON(), nullable=True),
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
            ["article_id"],
            ["substrate_article.id"],
            name="substrate_organization_mention_article_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["substrate_organization.id"],
            name="substrate_organization_mention_organization_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="substrate_organization_mention_pkey"),
        sa.UniqueConstraint(
            "article_id",
            "organization_id",
            name="uq_substrate_organization_mention_article_organization",
        ),
    )
    op.create_index(
        "ix_substrate_organization_mention_article_id",
        "substrate_organization_mention",
        ["article_id"],
    )
    op.create_index(
        "ix_substrate_organization_mention_organization_id",
        "substrate_organization_mention",
        ["organization_id"],
    )
    op.create_index(
        "ix_substrate_organization_mention_nature",
        "substrate_organization_mention",
        ["nature"],
    )
    op.create_index(
        "ix_substrate_organization_mention_needs_review",
        "substrate_organization_mention",
        ["needs_review"],
    )
    op.create_index(
        "ix_substrate_organization_mention_added",
        "substrate_organization_mention",
        ["added"],
    )
    op.create_index(
        "ix_substrate_organization_mention_edited",
        "substrate_organization_mention",
        ["edited"],
    )
    op.create_index(
        "ix_substrate_organization_mention_deleted",
        "substrate_organization_mention",
        ["deleted"],
    )
    op.create_index(
        "idx_substrate_organization_mention_article_review",
        "substrate_organization_mention",
        ["article_id", "needs_review", "deleted"],
    )
    op.create_index(
        "idx_substrate_organization_mention_organization",
        "substrate_organization_mention",
        ["organization_id", "deleted"],
    )

    op.create_table(
        "substrate_organization_mention_occurrence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_mention_id", sa.Integer(), nullable=False),
        sa.Column(
            "source_kind",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'system_extraction'"),
        ),
        sa.Column("source_details_json", sa.JSON(), nullable=True),
        sa.Column("mention_text", sa.Text(), nullable=False),
        sa.Column("quote_text", sa.Text(), nullable=True),
        sa.Column("start_char", sa.Integer(), nullable=True),
        sa.Column("end_char", sa.Integer(), nullable=True),
        sa.Column("occurrence_order", sa.Integer(), nullable=True),
        sa.Column(
            "labels_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("suppressed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
            ["organization_mention_id"],
            ["substrate_organization_mention.id"],
            name="substrate_organization_mention_occurrence_organization_mention_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="substrate_organization_mention_occurrence_pkey"),
    )
    op.create_index(
        "ix_substrate_organization_mention_occurrence_organization_mention_id",
        "substrate_organization_mention_occurrence",
        ["organization_mention_id"],
    )
    op.create_index(
        "ix_substrate_organization_mention_occurrence_suppressed",
        "substrate_organization_mention_occurrence",
        ["suppressed"],
    )
    op.create_index(
        "idx_substrate_organization_occurrence_mention_source",
        "substrate_organization_mention_occurrence",
        ["organization_mention_id", "source_kind", "suppressed"],
    )

    op.create_table(
        "stylebook_organization_alias",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_canonical_id", sa.Text(), nullable=False),
        sa.Column("alias_text", sa.Text(), nullable=False),
        sa.Column("normalized_alias", sa.Text(), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.Column(
            "suppressed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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
            ["organization_canonical_id"],
            ["stylebook_organization_canonical.id"],
            name="stylebook_organization_alias_organization_canonical_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_organization_alias_pkey"),
        sa.UniqueConstraint(
            "organization_canonical_id",
            "normalized_alias",
            name="uq_stylebook_organization_alias_canonical_normalized",
        ),
    )
    op.create_index(
        "ix_stylebook_organization_alias_organization_canonical_id",
        "stylebook_organization_alias",
        ["organization_canonical_id"],
    )
    op.create_index(
        "ix_stylebook_organization_alias_normalized",
        "stylebook_organization_alias",
        ["normalized_alias"],
    )
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "CREATE INDEX ix_stylebook_organization_alias_norm_trgm "
                "ON stylebook_organization_alias USING gin (normalized_alias gin_trgm_ops)"
            )
        )

    op.create_table(
        "stylebook_organization_meta",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("stylebook_organization_canonical_id", sa.Text(), nullable=False),
        sa.Column("meta_type", sa.Text(), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=True),
        sa.Column("added", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("edited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="stylebook_organization_meta_project_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_organization_canonical_id"],
            ["stylebook_organization_canonical.id"],
            name="stylebook_organization_meta_stylebook_organization_canonical_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_organization_meta_pkey"),
    )
    op.create_index(
        "ix_stylebook_organization_meta_project_id",
        "stylebook_organization_meta",
        ["project_id"],
    )
    op.create_index(
        "ix_stylebook_organization_meta_stylebook_organization_canonical_id",
        "stylebook_organization_meta",
        ["stylebook_organization_canonical_id"],
    )
    op.create_index(
        "ix_stylebook_organization_meta_meta_type",
        "stylebook_organization_meta",
        ["meta_type"],
    )
    op.create_index(
        "ix_stylebook_organization_meta_canonical_type",
        "stylebook_organization_meta",
        ["stylebook_organization_canonical_id", "meta_type"],
    )

    op.create_table(
        "substrate_organization_semantic_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("organization_mention_id", sa.Integer(), nullable=False),
        sa.Column("organization_mention_occurrence_id", sa.Integer(), nullable=False),
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
            name="substrate_organization_sem_doc_project_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["substrate_article.id"],
            name="substrate_organization_sem_doc_article_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["substrate_organization.id"],
            name="substrate_organization_sem_doc_organization_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_mention_id"],
            ["substrate_organization_mention.id"],
            name="substrate_organization_sem_doc_mention_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_mention_occurrence_id"],
            ["substrate_organization_mention_occurrence.id"],
            name="substrate_organization_sem_doc_occurrence_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="substrate_organization_semantic_document_pkey"),
        sa.UniqueConstraint(
            "organization_mention_occurrence_id",
            name="uq_substrate_organization_sem_doc_occurrence",
        ),
    )
    op.create_index(
        "ix_substrate_organization_sem_doc_project_id",
        "substrate_organization_semantic_document",
        ["project_id"],
    )
    op.create_index(
        "ix_substrate_organization_sem_doc_article_id",
        "substrate_organization_semantic_document",
        ["article_id"],
    )
    op.create_index(
        "ix_substrate_organization_sem_doc_organization_id",
        "substrate_organization_semantic_document",
        ["organization_id"],
    )
    op.create_index(
        "ix_substrate_organization_sem_doc_organization_mention_id",
        "substrate_organization_semantic_document",
        ["organization_mention_id"],
    )
    op.create_index(
        "ix_substrate_organization_sem_doc_organization_mention_occurrence_id",
        "substrate_organization_semantic_document",
        ["organization_mention_occurrence_id"],
    )
    op.create_index(
        "ix_substrate_organization_sem_doc_source_hash",
        "substrate_organization_semantic_document",
        ["source_hash"],
    )
    op.create_index(
        "idx_substrate_organization_sem_doc_project_article",
        "substrate_organization_semantic_document",
        ["project_id", "article_id"],
    )
    op.create_index(
        "idx_substrate_organization_sem_doc_project_organization",
        "substrate_organization_semantic_document",
        ["project_id", "organization_id"],
    )
    op.create_index(
        "idx_substrate_organization_sem_doc_project_status",
        "substrate_organization_semantic_document",
        ["project_id", "embedding_status", "active"],
    )
    op.create_index(
        "idx_substrate_organization_sem_doc_project_active",
        "substrate_organization_semantic_document",
        ["project_id", "active", "stale"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("substrate_organization_semantic_document")
    op.drop_table("stylebook_organization_meta")
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("DROP INDEX IF EXISTS ix_stylebook_organization_alias_norm_trgm"))
    op.drop_table("stylebook_organization_alias")
    op.drop_table("substrate_organization_mention_occurrence")
    op.drop_table("substrate_organization_mention")
    op.drop_constraint(
        "stylebook_organization_canonical_primary_substrate_organization_id_fkey",
        "stylebook_organization_canonical",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_stylebook_organization_canonical_primary_substrate_organization_id",
        table_name="stylebook_organization_canonical",
    )
    op.drop_column("stylebook_organization_canonical", "primary_substrate_organization_id")
    if bind.dialect.name == "postgresql":
        op.drop_index(
            "ix_substrate_organization_project_pending_queue",
            table_name="substrate_organization",
        )
    op.drop_table("substrate_organization")
    op.drop_table("stylebook_organization_canonical")
