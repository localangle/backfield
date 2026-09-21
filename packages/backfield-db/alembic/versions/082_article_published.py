"""Add optional published timestamp on substrate articles."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "082_article_published"
down_revision: str | None = "081_conn_evidence_fk"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "substrate_article",
        sa.Column("published", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_substrate_article_project_published",
        "substrate_article",
        ["project_id", "published"],
    )
    op.create_index(
        "idx_substrate_article_project_updated",
        "substrate_article",
        ["project_id", "updated"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_substrate_article_project_updated",
        table_name="substrate_article",
    )
    op.drop_index(
        "idx_substrate_article_project_published",
        table_name="substrate_article",
    )
    op.drop_column("substrate_article", "published")
