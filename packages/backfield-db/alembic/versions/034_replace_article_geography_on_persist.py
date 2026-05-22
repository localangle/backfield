"""One-shot flag: next DBOutput persist replaces machine geography for the article."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "034_replace_article_geography"
down_revision: Union[str, None] = "033_agate_processed_item_overlay"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agate_run",
        sa.Column(
            "replace_article_geography_on_persist",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "agate_processed_item",
        sa.Column(
            "replace_article_geography_on_persist",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("agate_processed_item", "replace_article_geography_on_persist")
    op.drop_column("agate_run", "replace_article_geography_on_persist")
