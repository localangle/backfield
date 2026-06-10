"""Image embedding storage (EmbedImages node / DBOutput persist)."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "044_image_embedding"
down_revision: Union[str, None] = "043_article_meta_multi_subject"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def _embedding_column():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from pgvector.sqlalchemy import Vector

        return sa.Column("embedding", Vector(1536), nullable=True)
    return sa.Column("embedding", sa.Text(), nullable=True)


def upgrade() -> None:
    op.create_table(
        "substrate_image_embedding",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("substrate_image_id", sa.Integer(), nullable=False),
        sa.Column("generated_text", sa.Text(), nullable=False),
        sa.Column("vision_model", sa.Text(), nullable=True),
        sa.Column("vision_ai_model_config_id", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding_ai_model_config_id", sa.Text(), nullable=True),
        _embedding_column(),
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
            ["substrate_image_id"],
            ["substrate_image.id"],
            name="substrate_image_embedding_substrate_image_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="substrate_image_embedding_pkey"),
        sa.UniqueConstraint(
            "substrate_image_id",
            name="uq_substrate_image_embedding_image_id",
        ),
    )
    op.create_index(
        "ix_substrate_image_embedding_substrate_image_id",
        "substrate_image_embedding",
        ["substrate_image_id"],
        unique=True,
    )
    op.create_index(
        "ix_substrate_image_embedding_embedding_model",
        "substrate_image_embedding",
        ["embedding_model"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_substrate_image_embedding_embedding_model",
        table_name="substrate_image_embedding",
    )
    op.drop_index(
        "ix_substrate_image_embedding_substrate_image_id",
        table_name="substrate_image_embedding",
    )
    op.drop_table("substrate_image_embedding")
