"""Unique stylebook name per org; slug redirect history for renames."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023_sb_name_unique_redirect"
down_revision: Union[str, None] = "022_sb_canon_district"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_stylebook_organization_name",
        "stylebook",
        ["organization_id", "name"],
    )
    op.create_table(
        "stylebook_slug_redirect",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("old_slug", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["backfield_organization.id"],
            name="stylebook_slug_redirect_organization_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_id"],
            ["stylebook.id"],
            name="stylebook_slug_redirect_stylebook_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_slug_redirect_pkey"),
        sa.UniqueConstraint(
            "organization_id",
            "old_slug",
            name="uq_stylebook_slug_redirect_org_old_slug",
        ),
    )
    op.create_index(
        "ix_stylebook_slug_redirect_organization_id",
        "stylebook_slug_redirect",
        ["organization_id"],
    )
    op.create_index(
        "ix_stylebook_slug_redirect_stylebook_id",
        "stylebook_slug_redirect",
        ["stylebook_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_stylebook_slug_redirect_stylebook_id",
        table_name="stylebook_slug_redirect",
    )
    op.drop_index(
        "ix_stylebook_slug_redirect_organization_id",
        table_name="stylebook_slug_redirect",
    )
    op.drop_table("stylebook_slug_redirect")
    op.drop_constraint("uq_stylebook_organization_name", "stylebook", type_="unique")
