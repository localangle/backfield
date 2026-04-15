"""Add backfield_workspace_membership for user workspace access.

Revision ID: 004_ws_membership
Revises: 003_def_ws_general
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_ws_membership"
down_revision: Union[str, None] = "003_def_ws_general"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backfield_workspace_membership",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["backfield_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["backfield_workspace.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "workspace_id", name="uq_backfield_ws_member_user_ws"),
    )
    op.create_index(
        "ix_backfield_workspace_membership_user_id",
        "backfield_workspace_membership",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_workspace_membership_workspace_id",
        "backfield_workspace_membership",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_backfield_workspace_membership_workspace_id",
        table_name="backfield_workspace_membership",
    )
    op.drop_index(
        "ix_backfield_workspace_membership_user_id",
        table_name="backfield_workspace_membership",
    )
    op.drop_table("backfield_workspace_membership")
