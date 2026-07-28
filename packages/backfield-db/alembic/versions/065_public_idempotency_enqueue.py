"""Add retryable enqueue state to public idempotency records."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "065_public_idempotency_enqueue"
down_revision: Union[str, None] = "064_public_idempotency"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "backfield_public_idempotency_record",
        sa.Column("enqueue_task_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "backfield_public_idempotency_record",
        sa.Column("enqueue_args_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "backfield_public_idempotency_record",
        sa.Column(
            "enqueue_state",
            sa.Text(),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "backfield_public_idempotency_record",
        sa.Column("enqueue_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "backfield_public_idempotency_record",
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "backfield_public_idempotency_record",
        sa.Column(
            "enqueue_attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "backfield_public_idempotency_record",
        sa.Column("enqueue_last_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_backfield_public_idempotency_enqueue_state",
        "backfield_public_idempotency_record",
        ["enqueue_state"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_backfield_public_idempotency_enqueue_state",
        table_name="backfield_public_idempotency_record",
    )
    op.drop_column("backfield_public_idempotency_record", "enqueue_last_error")
    op.drop_column("backfield_public_idempotency_record", "enqueue_attempt_count")
    op.drop_column("backfield_public_idempotency_record", "enqueued_at")
    op.drop_column("backfield_public_idempotency_record", "enqueue_claimed_at")
    op.drop_column("backfield_public_idempotency_record", "enqueue_state")
    op.drop_column("backfield_public_idempotency_record", "enqueue_args_json")
    op.drop_column("backfield_public_idempotency_record", "enqueue_task_name")
