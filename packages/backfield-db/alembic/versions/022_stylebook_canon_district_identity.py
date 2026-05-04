"""District identity columns on stylebook_location_canonical."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022_sb_canon_district"
down_revision: Union[str, None] = "021_sb_canon_jurisdiction"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stylebook_location_canonical",
        sa.Column("district_kind", sa.Text(), nullable=True),
    )
    op.add_column(
        "stylebook_location_canonical",
        sa.Column("district_number", sa.Text(), nullable=True),
    )
    op.add_column(
        "stylebook_location_canonical",
        sa.Column("district_key", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_stylebook_location_canonical_district_key",
        "stylebook_location_canonical",
        ["district_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_stylebook_location_canonical_district_key",
        table_name="stylebook_location_canonical",
    )
    op.drop_column("stylebook_location_canonical", "district_key")
    op.drop_column("stylebook_location_canonical", "district_number")
    op.drop_column("stylebook_location_canonical", "district_kind")
