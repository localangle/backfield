"""Add full-text search index on substrate_article headline, body, and URL."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "047_substrate_article_fulltext"
down_revision: Union[str, None] = "046_agate_graph_description"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_substrate_article_fulltext
        ON substrate_article
        USING gin(
            to_tsvector(
                'english',
                coalesce(headline, '') || ' ' || coalesce(text, '') || ' ' || coalesce(url, '')
            )
        )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS idx_substrate_article_fulltext")
