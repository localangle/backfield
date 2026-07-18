"""Add short-lived public API idempotency records."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "064_public_idempotency"
down_revision: Union[str, None] = "063_stylebook_activity"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backfield_public_idempotency_record",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="backfield_public_idempotency_project_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agate_run.id"],
            name="backfield_public_idempotency_run_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="backfield_public_idempotency_record_pkey"),
        sa.UniqueConstraint(
            "project_id",
            "operation",
            "idempotency_key",
            name="uq_backfield_public_idempotency_scope",
        ),
    )
    op.create_index(
        "ix_backfield_public_idempotency_expires",
        "backfield_public_idempotency_record",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_public_idempotency_run",
        "backfield_public_idempotency_record",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_backfield_public_idempotency_run",
        table_name="backfield_public_idempotency_record",
    )
    op.drop_index(
        "ix_backfield_public_idempotency_expires",
        table_name="backfield_public_idempotency_record",
    )
    op.drop_table("backfield_public_idempotency_record")
