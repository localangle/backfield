"""Record a reason and the cleanup run on dismissals."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "085_cleanup_dismissal_reason"
down_revision: str | None = "084_cleanup_run_ledger"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("stylebook_cleanup_dismissal", sa.Column("reason_code", sa.Text(), nullable=True))
    op.add_column("stylebook_cleanup_dismissal", sa.Column("run_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "stylebook_cleanup_dismissal_run_id_fkey",
        "stylebook_cleanup_dismissal",
        "stylebook_cleanup_run",
        ["run_id"],
        ["id"],
    )
    op.create_index(
        "ix_stylebook_cleanup_dismissal_run_id", "stylebook_cleanup_dismissal", ["run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_stylebook_cleanup_dismissal_run_id", table_name="stylebook_cleanup_dismissal")
    op.drop_constraint(
        "stylebook_cleanup_dismissal_run_id_fkey", "stylebook_cleanup_dismissal", type_="foreignkey"
    )
    op.drop_column("stylebook_cleanup_dismissal", "run_id")
    op.drop_column("stylebook_cleanup_dismissal", "reason_code")
