"""Let a cleanup ledger row have no canonical (a deferred candidate is not linked to one)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "086_cleanup_action_no_canonical"
down_revision: str | None = "085_cleanup_dismissal_reason"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "stylebook_cleanup_action", "canonical_id", existing_type=sa.Text(), nullable=True
    )


def downgrade() -> None:
    # A ledger row without a canonical cannot be kept once the column is required again.
    op.execute("DELETE FROM stylebook_cleanup_action WHERE canonical_id IS NULL")
    op.alter_column(
        "stylebook_cleanup_action", "canonical_id", existing_type=sa.Text(), nullable=False
    )
