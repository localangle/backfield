"""First-token blocking index for organization duplicate cleanup."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "055_sb_org_first_token_idx"
down_revision: Union[str, None] = "054_sb_person_org_dup_idx"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_stylebook_organization_canonical_stylebook_first_token
        ON stylebook_organization_canonical (
            stylebook_id,
            lower(trim(split_part(label, ' ', 1)))
        )
        WHERE length(trim(label)) > 0
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "DROP INDEX IF EXISTS ix_stylebook_organization_canonical_stylebook_first_token"
    )
