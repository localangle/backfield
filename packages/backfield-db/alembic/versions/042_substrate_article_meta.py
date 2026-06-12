"""Article-level metadata tag storage (Article Metadata node / DBOutput persist)."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "042_substrate_article_meta"
down_revision: Union[str, None] = "041_article_embedding"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "substrate_article_meta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("meta_type", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("prompt_preset", sa.Text(), nullable=True),
        sa.Column("source_run_id", sa.String(), nullable=True),
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
            name="substrate_article_meta_article_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["agate_run.id"],
            name="substrate_article_meta_source_run_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="substrate_article_meta_pkey"),
        sa.UniqueConstraint(
            "article_id",
            "meta_type",
            name="uq_substrate_article_meta_article_id_meta_type",
        ),
    )
    op.create_index(
        "ix_substrate_article_meta_article_id",
        "substrate_article_meta",
        ["article_id"],
        unique=False,
    )
    op.create_index(
        "ix_substrate_article_meta_meta_type",
        "substrate_article_meta",
        ["meta_type"],
        unique=False,
    )
    op.create_index(
        "ix_substrate_article_meta_source_run_id",
        "substrate_article_meta",
        ["source_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_substrate_article_meta_source_run_id",
        table_name="substrate_article_meta",
    )
    op.drop_index(
        "ix_substrate_article_meta_meta_type",
        table_name="substrate_article_meta",
    )
    op.drop_index(
        "ix_substrate_article_meta_article_id",
        table_name="substrate_article_meta",
    )
    op.drop_table("substrate_article_meta")
