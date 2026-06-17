"""GIN btree index on stylebook_location_canonical primary name for cleanup duplicate blocking."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "053_sb_loc_canon_head_label"
down_revision: Union[str, None] = "052_sb_loc_label_trgm"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_stylebook_location_canonical_stylebook_head_label
        ON stylebook_location_canonical (
            stylebook_id,
            lower(trim(split_part(label, ',', 1)))
        )
        WHERE length(trim(label)) > 0
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "DROP INDEX IF EXISTS ix_stylebook_location_canonical_stylebook_head_label"
    )
