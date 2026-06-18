"""Persist stylebook cleanup AI review runs and proposals."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "057_stylebook_cleanup_ai_review"
down_revision: Union[str, None] = "056_stylebook_cleanup_dismissal"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stylebook_cleanup_ai_review",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("check_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("provider_model_id", sa.Text(), nullable=False),
        sa.Column("ai_model_config_id", sa.Text(), nullable=True),
        sa.Column("cluster_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_cluster_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("proposal_count", sa.Integer(), server_default="0", nullable=False),
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
            name="stylebook_cleanup_ai_review_ai_model_config_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["backfield_user.id"],
            name="stylebook_cleanup_ai_review_created_by_user_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_id"],
            ["stylebook.id"],
            name="stylebook_cleanup_ai_review_stylebook_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_cleanup_ai_review_pkey"),
    )
    op.create_index(
        "ix_stylebook_cleanup_ai_review_stylebook_check",
        "stylebook_cleanup_ai_review",
        ["stylebook_id", "check_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_cleanup_ai_review_stylebook_id",
        "stylebook_cleanup_ai_review",
        ["stylebook_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_cleanup_ai_review_ai_model_config_id",
        "stylebook_cleanup_ai_review",
        ["ai_model_config_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_cleanup_ai_review_created_by_user_id",
        "stylebook_cleanup_ai_review",
        ["created_by_user_id"],
        unique=False,
    )

    op.create_table(
        "stylebook_cleanup_ai_proposal",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("review_id", sa.Text(), nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("check_id", sa.Text(), nullable=False),
        sa.Column("cluster_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_canonical_id", sa.Text(), nullable=True),
        sa.Column("member_ids_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["resolved_by_user_id"],
            ["backfield_user.id"],
            name="stylebook_cleanup_ai_proposal_resolved_by_user_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["stylebook_cleanup_ai_review.id"],
            name="stylebook_cleanup_ai_proposal_review_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_id"],
            ["stylebook.id"],
            name="stylebook_cleanup_ai_proposal_stylebook_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_cleanup_ai_proposal_pkey"),
    )
    op.create_index(
        "ix_stylebook_cleanup_ai_proposal_stylebook_check_status",
        "stylebook_cleanup_ai_proposal",
        ["stylebook_id", "check_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_cleanup_ai_proposal_review_id",
        "stylebook_cleanup_ai_proposal",
        ["review_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_cleanup_ai_proposal_stylebook_id",
        "stylebook_cleanup_ai_proposal",
        ["stylebook_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_cleanup_ai_proposal_resolved_by_user_id",
        "stylebook_cleanup_ai_proposal",
        ["resolved_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_stylebook_cleanup_ai_proposal_resolved_by_user_id",
        table_name="stylebook_cleanup_ai_proposal",
    )
    op.drop_index(
        "ix_stylebook_cleanup_ai_proposal_stylebook_id",
        table_name="stylebook_cleanup_ai_proposal",
    )
    op.drop_index(
        "ix_stylebook_cleanup_ai_proposal_review_id",
        table_name="stylebook_cleanup_ai_proposal",
    )
    op.drop_index(
        "ix_stylebook_cleanup_ai_proposal_stylebook_check_status",
        table_name="stylebook_cleanup_ai_proposal",
    )
    op.drop_table("stylebook_cleanup_ai_proposal")

    op.drop_index(
        "ix_stylebook_cleanup_ai_review_created_by_user_id",
        table_name="stylebook_cleanup_ai_review",
    )
    op.drop_index(
        "ix_stylebook_cleanup_ai_review_ai_model_config_id",
        table_name="stylebook_cleanup_ai_review",
    )
    op.drop_index(
        "ix_stylebook_cleanup_ai_review_stylebook_id",
        table_name="stylebook_cleanup_ai_review",
    )
    op.drop_index(
        "ix_stylebook_cleanup_ai_review_stylebook_check",
        table_name="stylebook_cleanup_ai_review",
    )
    op.drop_table("stylebook_cleanup_ai_review")
