"""Person entity schema: Stylebook canonical trio + substrate trio.

Revision id must fit ``alembic_version.version_num`` (varchar(32)).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "036_person_schema"
down_revision: Union[str, None] = "035_reviewed_output_json"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "stylebook_person_canonical",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("affiliation", sa.Text(), nullable=True),
        sa.Column(
            "public_figure",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("person_type", sa.Text(), nullable=True),
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
            name="stylebook_person_canonical_stylebook_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_person_canonical_pkey"),
        sa.UniqueConstraint(
            "stylebook_id",
            "slug",
            name="uq_stylebook_person_canonical_stylebook_slug",
        ),
    )
    op.create_index(
        "ix_stylebook_person_canonical_stylebook_id",
        "stylebook_person_canonical",
        ["stylebook_id"],
    )
    op.create_index(
        "ix_stylebook_person_canonical_stylebook_type",
        "stylebook_person_canonical",
        ["stylebook_id", "person_type"],
    )
    op.create_index(
        "ix_stylebook_person_canonical_stylebook_public_figure",
        "stylebook_person_canonical",
        ["stylebook_id", "public_figure"],
    )

    op.create_table(
        "substrate_person",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("affiliation", sa.Text(), nullable=True),
        sa.Column(
            "public_figure",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("person_type", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'provisional'"),
        ),
        sa.Column("stylebook_person_canonical_id", sa.Text(), nullable=True),
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
            name="substrate_person_project_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_person_canonical_id"],
            ["stylebook_person_canonical.id"],
            name="substrate_person_stylebook_person_canonical_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="substrate_person_pkey"),
        sa.UniqueConstraint(
            "project_id",
            "external_source",
            "external_id",
            name="uq_substrate_person_project_external",
        ),
        sa.UniqueConstraint(
            "project_id",
            "identity_fingerprint",
            name="uq_substrate_person_project_fingerprint",
        ),
    )
    op.create_index("ix_substrate_person_project_id", "substrate_person", ["project_id"])
    op.create_index(
        "ix_substrate_person_normalized_name",
        "substrate_person",
        ["normalized_name"],
    )
    op.create_index(
        "idx_substrate_person_project_status",
        "substrate_person",
        ["project_id", "status"],
    )
    op.create_index(
        "idx_substrate_person_project_name",
        "substrate_person",
        ["project_id", "normalized_name"],
    )
    op.create_index(
        "idx_substrate_person_project_type",
        "substrate_person",
        ["project_id", "person_type"],
    )
    op.create_index(
        "idx_substrate_person_project_public_figure",
        "substrate_person",
        ["project_id", "public_figure"],
    )
    op.create_index(
        "ix_substrate_person_stylebook_person_canonical_id",
        "substrate_person",
        ["stylebook_person_canonical_id"],
    )
    op.create_index(
        "ix_substrate_person_project_canonical",
        "substrate_person",
        ["project_id", "stylebook_person_canonical_id"],
    )
    op.create_index(
        "ix_substrate_person_project_link_status",
        "substrate_person",
        ["project_id", "canonical_link_status"],
    )
    if bind.dialect.name == "postgresql":
        op.create_index(
            "ix_substrate_person_project_pending_queue",
            "substrate_person",
            ["project_id"],
            postgresql_where=sa.text(
                "canonical_link_status = 'pending' AND stylebook_person_canonical_id IS NULL"
            ),
        )

    op.add_column(
        "stylebook_person_canonical",
        sa.Column("primary_substrate_person_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "stylebook_person_canonical_primary_substrate_person_id_fkey",
        "stylebook_person_canonical",
        "substrate_person",
        ["primary_substrate_person_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_stylebook_person_canonical_primary_substrate_person_id",
        "stylebook_person_canonical",
        ["primary_substrate_person_id"],
    )

    op.create_table(
        "substrate_person_mention",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
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
            name="substrate_person_mention_article_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["substrate_person.id"],
            name="substrate_person_mention_person_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="substrate_person_mention_pkey"),
        sa.UniqueConstraint(
            "article_id",
            "person_id",
            name="uq_substrate_person_mention_article_person",
        ),
    )
    op.create_index(
        "ix_substrate_person_mention_article_id",
        "substrate_person_mention",
        ["article_id"],
    )
    op.create_index(
        "ix_substrate_person_mention_person_id",
        "substrate_person_mention",
        ["person_id"],
    )
    op.create_index(
        "ix_substrate_person_mention_nature",
        "substrate_person_mention",
        ["nature"],
    )
    op.create_index(
        "ix_substrate_person_mention_needs_review",
        "substrate_person_mention",
        ["needs_review"],
    )
    op.create_index(
        "ix_substrate_person_mention_added",
        "substrate_person_mention",
        ["added"],
    )
    op.create_index(
        "ix_substrate_person_mention_edited",
        "substrate_person_mention",
        ["edited"],
    )
    op.create_index(
        "ix_substrate_person_mention_deleted",
        "substrate_person_mention",
        ["deleted"],
    )
    op.create_index(
        "idx_substrate_person_mention_article_review",
        "substrate_person_mention",
        ["article_id", "needs_review", "deleted"],
    )
    op.create_index(
        "idx_substrate_person_mention_person",
        "substrate_person_mention",
        ["person_id", "deleted"],
    )

    op.create_table(
        "substrate_person_mention_occurrence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("person_mention_id", sa.Integer(), nullable=False),
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
            ["person_mention_id"],
            ["substrate_person_mention.id"],
            name="substrate_person_mention_occurrence_person_mention_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="substrate_person_mention_occurrence_pkey"),
    )
    op.create_index(
        "ix_substrate_person_mention_occurrence_person_mention_id",
        "substrate_person_mention_occurrence",
        ["person_mention_id"],
    )
    op.create_index(
        "ix_substrate_person_mention_occurrence_suppressed",
        "substrate_person_mention_occurrence",
        ["suppressed"],
    )
    op.create_index(
        "idx_substrate_person_occurrence_mention_source",
        "substrate_person_mention_occurrence",
        ["person_mention_id", "source_kind", "suppressed"],
    )

    op.create_table(
        "stylebook_person_alias",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("person_canonical_id", sa.Text(), nullable=False),
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
            ["person_canonical_id"],
            ["stylebook_person_canonical.id"],
            name="stylebook_person_alias_person_canonical_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_person_alias_pkey"),
        sa.UniqueConstraint(
            "person_canonical_id",
            "normalized_alias",
            name="uq_stylebook_person_alias_canonical_normalized",
        ),
    )
    op.create_index(
        "ix_stylebook_person_alias_person_canonical_id",
        "stylebook_person_alias",
        ["person_canonical_id"],
    )
    op.create_index(
        "ix_stylebook_person_alias_normalized",
        "stylebook_person_alias",
        ["normalized_alias"],
    )
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "CREATE INDEX ix_stylebook_person_alias_norm_trgm "
                "ON stylebook_person_alias USING gin (normalized_alias gin_trgm_ops)"
            )
        )

    op.create_table(
        "stylebook_person_meta",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("stylebook_person_canonical_id", sa.Text(), nullable=False),
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
            name="stylebook_person_meta_project_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_person_canonical_id"],
            ["stylebook_person_canonical.id"],
            name="stylebook_person_meta_stylebook_person_canonical_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_person_meta_pkey"),
    )
    op.create_index(
        "ix_stylebook_person_meta_project_id",
        "stylebook_person_meta",
        ["project_id"],
    )
    op.create_index(
        "ix_stylebook_person_meta_stylebook_person_canonical_id",
        "stylebook_person_meta",
        ["stylebook_person_canonical_id"],
    )
    op.create_index(
        "ix_stylebook_person_meta_meta_type",
        "stylebook_person_meta",
        ["meta_type"],
    )
    op.create_index(
        "ix_stylebook_person_meta_canonical_type",
        "stylebook_person_meta",
        ["stylebook_person_canonical_id", "meta_type"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("stylebook_person_meta")
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("DROP INDEX IF EXISTS ix_stylebook_person_alias_norm_trgm"))
    op.drop_table("stylebook_person_alias")
    op.drop_table("substrate_person_mention_occurrence")
    op.drop_table("substrate_person_mention")
    op.drop_constraint(
        "stylebook_person_canonical_primary_substrate_person_id_fkey",
        "stylebook_person_canonical",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_stylebook_person_canonical_primary_substrate_person_id",
        table_name="stylebook_person_canonical",
    )
    op.drop_column("stylebook_person_canonical", "primary_substrate_person_id")
    if bind.dialect.name == "postgresql":
        op.drop_index(
            "ix_substrate_person_project_pending_queue",
            table_name="substrate_person",
        )
    op.drop_table("substrate_person")
    op.drop_table("stylebook_person_canonical")
