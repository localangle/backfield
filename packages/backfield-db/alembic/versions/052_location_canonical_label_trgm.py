"""GIN trigram index on stylebook_location_canonical.label for cleanup duplicate detection."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "052_location_canonical_label_trgm"
down_revision: Union[str, None] = "051_pi_substrate_article_id"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_stylebook_location_canonical_label_trgm
        ON stylebook_location_canonical
        USING gin (lower(label) gin_trgm_ops)
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_stylebook_location_canonical_label_trgm")
