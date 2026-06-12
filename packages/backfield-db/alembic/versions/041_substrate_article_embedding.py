"""Article-level text embedding storage (EmbedText node / DBOutput persist)."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "041_article_embedding"
down_revision: Union[str, None] = "040_sb_conn_evidence"
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
        "substrate_article_embedding",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("embedded_text", sa.Text(), nullable=False),
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
            ["article_id"],
            ["substrate_article.id"],
            name="substrate_article_embedding_article_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="substrate_article_embedding_pkey"),
        sa.UniqueConstraint("article_id", name="uq_substrate_article_embedding_article_id"),
    )
    op.create_index(
        "ix_substrate_article_embedding_article_id",
        "substrate_article_embedding",
        ["article_id"],
        unique=True,
    )
    op.create_index(
        "ix_substrate_article_embedding_embedding_model",
        "substrate_article_embedding",
        ["embedding_model"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_substrate_article_embedding_embedding_model",
        table_name="substrate_article_embedding",
    )
    op.drop_index(
        "ix_substrate_article_embedding_article_id",
        table_name="substrate_article_embedding",
    )
    op.drop_table("substrate_article_embedding")
