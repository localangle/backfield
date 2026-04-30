"""Add ``substrate_location.geocode_router_audit_json`` for AdvancedGeocodeAgent router audit.

Revision id must fit ``alembic_version.version_num`` (varchar(32)).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "020_sub_geocode_router_audit"
down_revision: Union[str, None] = "019_sb_loc_canon_uuid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    json_type = postgresql.JSONB(astext_type=sa.Text()) if is_pg else sa.JSON()
    op.add_column(
        "substrate_location",
        sa.Column("geocode_router_audit_json", json_type, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("substrate_location", "geocode_router_audit_json")
