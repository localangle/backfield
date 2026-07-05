"""Add stylebook activity event table for Recent feed."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "063_stylebook_activity"
down_revision: Union[str, None] = "062_stylebook_cleanup_check_run"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stylebook_activity",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("actor_type", sa.Text(), server_default="system", nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("entity_label", sa.Text(), nullable=True),
        sa.Column("related_entity_type", sa.Text(), nullable=True),
        sa.Column("related_entity_id", sa.Text(), nullable=True),
        sa.Column("related_entity_label", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["backfield_user.id"],
            name="stylebook_activity_actor_user_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="stylebook_activity_project_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_id"],
            ["stylebook.id"],
            name="stylebook_activity_stylebook_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_activity_pkey"),
    )
    op.create_index(
        "ix_stylebook_activity_stylebook_id",
        "stylebook_activity",
        ["stylebook_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_activity_project_id",
        "stylebook_activity",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_activity_actor_user_id",
        "stylebook_activity",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_activity_feed",
        "stylebook_activity",
        ["stylebook_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_activity_stylebook_event",
        "stylebook_activity",
        ["stylebook_id", "event_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_activity_stylebook_entity",
        "stylebook_activity",
        ["stylebook_id", "entity_type", "entity_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_activity_project_created",
        "stylebook_activity",
        ["project_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stylebook_activity_project_created", table_name="stylebook_activity")
    op.drop_index("ix_stylebook_activity_stylebook_entity", table_name="stylebook_activity")
    op.drop_index("ix_stylebook_activity_stylebook_event", table_name="stylebook_activity")
    op.drop_index("ix_stylebook_activity_feed", table_name="stylebook_activity")
    op.drop_index("ix_stylebook_activity_actor_user_id", table_name="stylebook_activity")
    op.drop_index("ix_stylebook_activity_project_id", table_name="stylebook_activity")
    op.drop_index("ix_stylebook_activity_stylebook_id", table_name="stylebook_activity")
    op.drop_table("stylebook_activity")
