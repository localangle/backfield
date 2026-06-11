"""Custom extracted record storage (Custom Extract node / DBOutput persist)."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "045_substrate_custom_record"
down_revision: Union[str, None] = "044_image_embedding"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "substrate_custom_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("record_type", sa.Text(), nullable=False),
        sa.Column("record_index", sa.Integer(), nullable=False),
        sa.Column("fields_json", sa.JSON(), nullable=False),
        sa.Column("mentions_json", sa.JSON(), nullable=False),
        sa.Column("field_schema_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
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
            name="substrate_custom_record_article_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["agate_run.id"],
            name="substrate_custom_record_source_run_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="substrate_custom_record_pkey"),
        sa.UniqueConstraint(
            "article_id",
            "record_type",
            "record_index",
            name="uq_substrate_custom_record_article_type_index",
        ),
    )
    op.create_index(
        "ix_substrate_custom_record_article_id",
        "substrate_custom_record",
        ["article_id"],
        unique=False,
    )
    op.create_index(
        "ix_substrate_custom_record_record_type",
        "substrate_custom_record",
        ["record_type"],
        unique=False,
    )
    op.create_index(
        "ix_substrate_custom_record_source_run_id",
        "substrate_custom_record",
        ["source_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_substrate_custom_record_source_run_id",
        table_name="substrate_custom_record",
    )
    op.drop_index(
        "ix_substrate_custom_record_record_type",
        table_name="substrate_custom_record",
    )
    op.drop_index(
        "ix_substrate_custom_record_article_id",
        table_name="substrate_custom_record",
    )
    op.drop_table("substrate_custom_record")
