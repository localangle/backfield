"""Replace the processed-item run index with a run/status index."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "066_agate_pi_run_status"
down_revision: str | None = "065_public_idempotency_enqueue"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "agate_processed_item"
_RUN_INDEX = "ix_agate_processed_item_run_id"
_RUN_STATUS_INDEX = "ix_agate_processed_item_run_status"


def upgrade() -> None:
    # Concurrent DDL keeps active batch-item writes available during release migration.
    with op.get_context().autocommit_block():
        op.create_index(
            _RUN_STATUS_INDEX,
            _TABLE,
            ["run_id", "status"],
            unique=False,
            postgresql_concurrently=True,
        )
        op.drop_index(
            _RUN_INDEX,
            table_name=_TABLE,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            _RUN_INDEX,
            _TABLE,
            ["run_id"],
            unique=False,
            postgresql_concurrently=True,
        )
        op.drop_index(
            _RUN_STATUS_INDEX,
            table_name=_TABLE,
            postgresql_concurrently=True,
        )
