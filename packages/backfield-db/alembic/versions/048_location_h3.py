"""Enable H3 extension and add native H3 cell metadata to location tables."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "048_location_h3"
down_revision: Union[str, None] = "047_substrate_article_fulltext"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None

_LOCATION_TABLES = (
    "substrate_location",
    "substrate_location_cache",
    "stylebook_location_canonical",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS h3"))

    for table in _LOCATION_TABLES:
        op.add_column(table, sa.Column("h3_cell", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("h3_resolution", sa.Integer(), nullable=True))

    op.create_index(
        "idx_substrate_location_project_h3_resolution",
        "substrate_location",
        ["project_id", "h3_resolution"],
    )
    op.create_index(
        "idx_substrate_location_project_h3_cell",
        "substrate_location",
        ["project_id", "h3_cell"],
    )
    op.create_index(
        "idx_substrate_location_cache_project_h3_resolution",
        "substrate_location_cache",
        ["project_id", "h3_resolution"],
    )
    op.create_index(
        "idx_substrate_location_cache_project_h3_cell",
        "substrate_location_cache",
        ["project_id", "h3_cell"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index("idx_substrate_location_cache_project_h3_cell", table_name="substrate_location_cache")
    op.drop_index(
        "idx_substrate_location_cache_project_h3_resolution",
        table_name="substrate_location_cache",
    )
    op.drop_index("idx_substrate_location_project_h3_cell", table_name="substrate_location")
    op.drop_index("idx_substrate_location_project_h3_resolution", table_name="substrate_location")

    for table in reversed(_LOCATION_TABLES):
        op.drop_column(table, "h3_resolution")
        op.drop_column(table, "h3_cell")
