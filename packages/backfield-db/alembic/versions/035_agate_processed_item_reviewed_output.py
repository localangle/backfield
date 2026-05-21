"""Materialized reviewed output JSON on agate_processed_item."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "035_agate_processed_item_reviewed_output"
down_revision: Union[str, None] = "034_replace_article_geography"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agate_processed_item",
        sa.Column("reviewed_output_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agate_processed_item", "reviewed_output_json")
