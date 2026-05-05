"""Per-stylebook membership roles (editors)."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "024_stylebook_membership"
down_revision: Union[str, None] = "023_sb_name_unique_redirect"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stylebook_membership",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_id"],
            ["stylebook.id"],
            name="stylebook_membership_stylebook_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["backfield_user.id"],
            name="stylebook_membership_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_membership_pkey"),
        sa.UniqueConstraint(
            "stylebook_id",
            "user_id",
            name="uq_stylebook_member_stylebook_user",
        ),
    )
    op.create_index(
        "ix_stylebook_membership_stylebook_id",
        "stylebook_membership",
        ["stylebook_id"],
    )
    op.create_index(
        "ix_stylebook_membership_user_id",
        "stylebook_membership",
        ["user_id"],
    )
    op.create_index(
        "ix_stylebook_membership_stylebook_role",
        "stylebook_membership",
        ["stylebook_id", "role"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_stylebook_membership_stylebook_role",
        table_name="stylebook_membership",
    )
    op.drop_index(
        "ix_stylebook_membership_user_id",
        table_name="stylebook_membership",
    )
    op.drop_index(
        "ix_stylebook_membership_stylebook_id",
        table_name="stylebook_membership",
    )
    op.drop_table("stylebook_membership")

