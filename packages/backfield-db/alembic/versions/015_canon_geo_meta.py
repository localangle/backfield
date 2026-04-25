"""Add location_type and formatted_address to stylebook_location_canonical.

Catalog rows carry authoritative geography hints separate from per-project substrate rows.

Revision id must fit ``alembic_version.version_num`` (varchar(32)).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_canon_geo_meta"
down_revision: Union[str, None] = "014_pg_trgm_canon_geom"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stylebook_location_canonical",
        sa.Column("location_type", sa.Text(), nullable=True),
    )
    op.add_column(
        "stylebook_location_canonical",
        sa.Column("formatted_address", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stylebook_location_canonical", "formatted_address")
    op.drop_column("stylebook_location_canonical", "location_type")
