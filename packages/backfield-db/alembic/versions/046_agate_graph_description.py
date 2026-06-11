"""Add optional description to agate_graph."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "046_agate_graph_description"
down_revision: Union[str, None] = "045_substrate_custom_record"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agate_graph",
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("agate_graph", "description")
