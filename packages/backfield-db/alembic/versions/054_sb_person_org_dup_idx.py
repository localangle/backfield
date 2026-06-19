"""Cleanup duplicate indexes for person and organization canonical labels."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "054_sb_person_org_dup_idx"
down_revision: Union[str, None] = "053_sb_loc_canon_head_label"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_stylebook_person_canonical_label_trgm
        ON stylebook_person_canonical
        USING gin (lower(label) gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_stylebook_organization_canonical_label_trgm
        ON stylebook_organization_canonical
        USING gin (lower(label) gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_stylebook_person_canonical_stylebook_first_token
        ON stylebook_person_canonical (
            stylebook_id,
            lower(trim(split_part(label, ' ', 1)))
        )
        WHERE length(trim(label)) > 0
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_stylebook_organization_canonical_stylebook_head_label
        ON stylebook_organization_canonical (
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
    op.execute("DROP INDEX IF EXISTS ix_stylebook_organization_canonical_stylebook_head_label")
    op.execute("DROP INDEX IF EXISTS ix_stylebook_person_canonical_stylebook_first_token")
    op.execute("DROP INDEX IF EXISTS ix_stylebook_organization_canonical_label_trgm")
    op.execute("DROP INDEX IF EXISTS ix_stylebook_person_canonical_label_trgm")
