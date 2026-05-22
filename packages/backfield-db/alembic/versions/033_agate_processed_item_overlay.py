"""Review overlay JSON + optimistic version on agate_processed_item."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "033_agate_processed_item_overlay"
down_revision: Union[str, None] = "032_stylebook_bundle_job"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agate_processed_item",
        sa.Column("overlay_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "agate_processed_item",
        sa.Column(
            "overlay_version",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("agate_processed_item", "overlay_version")
    op.drop_column("agate_processed_item", "overlay_json")
