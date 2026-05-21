"""Materialized reviewed output JSON on agate_processed_item."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "035_reviewed_output_json"
down_revision: Union[str, None] = "034_replace_article_geography"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {c["name"] for c in insp.get_columns("agate_processed_item")}
    if "reviewed_output_json" not in existing:
        op.add_column(
            "agate_processed_item",
            sa.Column("reviewed_output_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("agate_processed_item", "reviewed_output_json")
