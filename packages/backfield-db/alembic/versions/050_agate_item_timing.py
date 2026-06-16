"""Add processed-item started_at and per-node wall-clock timing table."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "050_agate_item_timing"
down_revision: Union[str, None] = "049_public_read_perf_indexes"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agate_processed_item",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "agate_node_timing",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("processed_item_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Text(), nullable=False),
        sa.Column("node_type", sa.Text(), nullable=False),
        sa.Column("elapsed_s", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["processed_item_id"],
            ["agate_processed_item.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agate_run.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agate_node_timing_run_id",
        "agate_node_timing",
        ["run_id"],
    )
    op.create_index(
        "ix_agate_node_timing_processed_item_id",
        "agate_node_timing",
        ["processed_item_id"],
    )
    op.create_index(
        "ix_agate_node_timing_node_type",
        "agate_node_timing",
        ["node_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_agate_node_timing_node_type", table_name="agate_node_timing")
    op.drop_index("ix_agate_node_timing_processed_item_id", table_name="agate_node_timing")
    op.drop_index("ix_agate_node_timing_run_id", table_name="agate_node_timing")
    op.drop_table("agate_node_timing")
    op.drop_column("agate_processed_item", "started_at")
