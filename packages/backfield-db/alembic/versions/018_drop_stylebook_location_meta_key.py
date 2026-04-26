"""Remove deprecated ``stylebook_location_meta.meta_key`` (legacy installs).

Revision id must fit ``alembic_version.version_num`` (varchar(32)).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018_drop_sb_loc_meta_key"
down_revision: Union[str, None] = "017_sb_loc_meta_conn"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_stylebook_location_meta_meta_key"))
    op.execute(sa.text("ALTER TABLE stylebook_location_meta DROP COLUMN IF EXISTS meta_key"))


def downgrade() -> None:
    op.add_column(
        "stylebook_location_meta",
        sa.Column("meta_key", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_stylebook_location_meta_meta_key",
        "stylebook_location_meta",
        ["meta_key"],
        unique=False,
    )
