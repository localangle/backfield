"""Link substrate_location to stylebook_location_canonical (editorial queue FK).

Substrate rows own the edge to a Stylebook canonical; canonicals may exist without
substrate. No history table in this revision.

Revision id must fit ``alembic_version.version_num`` (varchar(32)).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_substrate_sb_canon_fk"
down_revision: Union[str, None] = "011_stylebook_locations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "substrate_location",
        sa.Column("stylebook_location_canonical_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "substrate_location_stylebook_location_canonical_id_fkey",
        "substrate_location",
        "stylebook_location_canonical",
        ["stylebook_location_canonical_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_substrate_location_project_canonical",
        "substrate_location",
        ["project_id", "stylebook_location_canonical_id"],
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            "ix_substrate_location_project_open_queue",
            "substrate_location",
            ["project_id"],
            postgresql_where=sa.text("stylebook_location_canonical_id IS NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index(
            "ix_substrate_location_project_open_queue",
            table_name="substrate_location",
        )
    op.drop_index("ix_substrate_location_project_canonical", table_name="substrate_location")
    op.drop_constraint(
        "substrate_location_stylebook_location_canonical_id_fkey",
        "substrate_location",
        type_="foreignkey",
    )
    op.drop_column("substrate_location", "stylebook_location_canonical_id")
