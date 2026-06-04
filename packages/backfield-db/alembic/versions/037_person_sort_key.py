"""Add sort_key to person substrate and canonical tables."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "037_person_sort_key"
down_revision: Union[str, None] = "036_person_schema"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("substrate_person", sa.Column("sort_key", sa.Text(), nullable=True))
    op.add_column("stylebook_person_canonical", sa.Column("sort_key", sa.Text(), nullable=True))
    op.create_index(
        "ix_substrate_person_project_sort_key",
        "substrate_person",
        ["project_id", "sort_key"],
    )
    op.create_index(
        "ix_stylebook_person_canonical_stylebook_sort_key",
        "stylebook_person_canonical",
        ["stylebook_id", "sort_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_stylebook_person_canonical_stylebook_sort_key",
        table_name="stylebook_person_canonical",
    )
    op.drop_index("ix_substrate_person_project_sort_key", table_name="substrate_person")
    op.drop_column("stylebook_person_canonical", "sort_key")
    op.drop_column("substrate_person", "sort_key")
