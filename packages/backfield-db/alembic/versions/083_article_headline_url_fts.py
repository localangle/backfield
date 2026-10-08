"""Index project Articles search and flow lookup by project.

The headline/URL expression matches ``_headline_url_tsvector`` in
``api.project_processed_items``. It intentionally omits article body so project
Articles search does not use the public full-text index.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "083_article_headline_url_fts"
down_revision: str | None = "082_article_published"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_agate_graph_project_id", "agate_graph", ["project_id"])
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_substrate_article_headline_url_fts
        ON substrate_article
        USING gin (
            to_tsvector(
                'english',
                coalesce(headline, '') || ' ' || coalesce(url, '')
            )
        )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS idx_substrate_article_headline_url_fts")
    op.drop_index("ix_agate_graph_project_id", table_name="agate_graph")
