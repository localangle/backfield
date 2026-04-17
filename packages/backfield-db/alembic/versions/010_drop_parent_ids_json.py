"""Drop parent_ids_json from substrate_location.

GeocodeAgent no longer emits parent hierarchies; durable locations keep geometry
and provider identity only.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_drop_parent_ids_json"
down_revision: Union[str, None] = "009_rename_substrate_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("substrate_location", "parent_ids_json")


def downgrade() -> None:
    op.add_column(
        "substrate_location",
        sa.Column(
            "parent_ids_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
