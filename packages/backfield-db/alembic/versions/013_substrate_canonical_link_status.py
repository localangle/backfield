"""Substrate canonical_link_status + review reasons JSON.

Revision id must fit ``alembic_version.version_num`` (varchar(32)).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_substrate_slc_status"
down_revision: Union[str, None] = "012_substrate_sb_canon_fk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "substrate_location",
        sa.Column(
            "canonical_link_status",
            sa.Text(),
            nullable=False,
            server_default="unlinked",
        ),
    )
    op.add_column(
        "substrate_location",
        sa.Column("canonical_review_reasons_json", sa.JSON(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE substrate_location SET canonical_link_status = 'linked' "
            "WHERE stylebook_location_canonical_id IS NOT NULL"
        )
    )
    op.create_index(
        "ix_substrate_location_project_link_status",
        "substrate_location",
        ["project_id", "canonical_link_status"],
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            "ix_substrate_location_project_pending_queue",
            "substrate_location",
            ["project_id"],
            postgresql_where=sa.text(
                "canonical_link_status = 'pending' AND stylebook_location_canonical_id IS NULL"
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index(
            "ix_substrate_location_project_pending_queue",
            table_name="substrate_location",
        )
    op.drop_index("ix_substrate_location_project_link_status", table_name="substrate_location")
    op.drop_column("substrate_location", "canonical_review_reasons_json")
    op.drop_column("substrate_location", "canonical_link_status")
