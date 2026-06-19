"""Persist stylebook cleanup dismissals (duplicate pairs and list items)."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "056_stylebook_cleanup_dismissal"
down_revision: Union[str, None] = "055_sb_org_first_token_idx"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stylebook_cleanup_dismissal",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("check_id", sa.Text(), nullable=False),
        sa.Column("pair_key", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["backfield_user.id"],
            name="stylebook_cleanup_dismissal_created_by_user_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_id"],
            ["stylebook.id"],
            name="stylebook_cleanup_dismissal_stylebook_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_cleanup_dismissal_pkey"),
        sa.UniqueConstraint(
            "stylebook_id",
            "check_id",
            "pair_key",
            name="uq_stylebook_cleanup_dismissal_key",
        ),
    )
    op.create_index(
        "ix_stylebook_cleanup_dismissal_stylebook_check",
        "stylebook_cleanup_dismissal",
        ["stylebook_id", "check_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_cleanup_dismissal_stylebook_id",
        "stylebook_cleanup_dismissal",
        ["stylebook_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_cleanup_dismissal_created_by_user_id",
        "stylebook_cleanup_dismissal",
        ["created_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_stylebook_cleanup_dismissal_created_by_user_id",
        table_name="stylebook_cleanup_dismissal",
    )
    op.drop_index(
        "ix_stylebook_cleanup_dismissal_stylebook_id",
        table_name="stylebook_cleanup_dismissal",
    )
    op.drop_index(
        "ix_stylebook_cleanup_dismissal_stylebook_check",
        table_name="stylebook_cleanup_dismissal",
    )
    op.drop_table("stylebook_cleanup_dismissal")
