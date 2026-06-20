"""Persist stylebook candidate queue AI review runs."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "058_sb_candidate_ai_review"
down_revision: Union[str, None] = "057_stylebook_cleanup_ai_review"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stylebook_candidate_ai_review",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("provider_model_id", sa.Text(), nullable=False),
        sa.Column("ai_model_config_id", sa.Text(), nullable=True),
        sa.Column("candidate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("recommendation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ai_model_config_id"],
            ["backfield_ai_model_config.id"],
            name="stylebook_candidate_ai_review_ai_model_config_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["backfield_user.id"],
            name="stylebook_candidate_ai_review_created_by_user_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="stylebook_candidate_ai_review_project_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_id"],
            ["stylebook.id"],
            name="stylebook_candidate_ai_review_stylebook_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_candidate_ai_review_pkey"),
    )
    op.create_index(
        "ix_stylebook_candidate_ai_review_stylebook_project_entity",
        "stylebook_candidate_ai_review",
        ["stylebook_id", "project_id", "entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_candidate_ai_review_stylebook_id",
        "stylebook_candidate_ai_review",
        ["stylebook_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_candidate_ai_review_project_id",
        "stylebook_candidate_ai_review",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_candidate_ai_review_ai_model_config_id",
        "stylebook_candidate_ai_review",
        ["ai_model_config_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_candidate_ai_review_created_by_user_id",
        "stylebook_candidate_ai_review",
        ["created_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_stylebook_candidate_ai_review_created_by_user_id",
        table_name="stylebook_candidate_ai_review",
    )
    op.drop_index(
        "ix_stylebook_candidate_ai_review_ai_model_config_id",
        table_name="stylebook_candidate_ai_review",
    )
    op.drop_index(
        "ix_stylebook_candidate_ai_review_project_id",
        table_name="stylebook_candidate_ai_review",
    )
    op.drop_index(
        "ix_stylebook_candidate_ai_review_stylebook_id",
        table_name="stylebook_candidate_ai_review",
    )
    op.drop_index(
        "ix_stylebook_candidate_ai_review_stylebook_project_entity",
        table_name="stylebook_candidate_ai_review",
    )
    op.drop_table("stylebook_candidate_ai_review")
