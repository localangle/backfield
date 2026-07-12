"""Persist stylebook cleanup check runs and cached candidate results."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "062_stylebook_cleanup_check_run"
down_revision: Union[str, None] = "061_sb_conn_description"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stylebook_cleanup_check_run",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("check_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("scope_hash", sa.Text(), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=True),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["created_by_user_id"],
            ["backfield_user.id"],
            name="stylebook_cleanup_check_run_created_by_user_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_id"],
            ["stylebook.id"],
            name="stylebook_cleanup_check_run_stylebook_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_cleanup_check_run_pkey"),
    )
    op.create_index(
        "ix_stylebook_cleanup_check_run_lookup",
        "stylebook_cleanup_check_run",
        ["stylebook_id", "check_id", "scope_hash", "status", "completed_at"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_cleanup_check_run_latest",
        "stylebook_cleanup_check_run",
        ["stylebook_id", "check_id", "scope_hash", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_cleanup_check_run_stylebook_id",
        "stylebook_cleanup_check_run",
        ["stylebook_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_cleanup_check_run_created_by_user_id",
        "stylebook_cleanup_check_run",
        ["created_by_user_id"],
        unique=False,
    )

    op.create_table(
        "stylebook_cleanup_check_result",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("check_id", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("item_kind", sa.Text(), nullable=False),
        sa.Column("item_key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("canonical_ids_json", sa.JSON(), nullable=False),
        sa.Column("pair_keys_json", sa.JSON(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("searchable_text", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["stylebook_cleanup_check_run.id"],
            name="stylebook_cleanup_check_result_run_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_id"],
            ["stylebook.id"],
            name="stylebook_cleanup_check_result_stylebook_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_cleanup_check_result_pkey"),
        sa.UniqueConstraint(
            "run_id",
            "item_key",
            name="uq_stylebook_cleanup_check_result_item",
        ),
    )
    op.create_index(
        "ix_stylebook_cleanup_check_result_run_ordinal",
        "stylebook_cleanup_check_result",
        ["run_id", "ordinal"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_cleanup_check_result_stylebook_check",
        "stylebook_cleanup_check_result",
        ["stylebook_id", "check_id", "run_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_cleanup_check_result_run_id",
        "stylebook_cleanup_check_result",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_cleanup_check_result_stylebook_id",
        "stylebook_cleanup_check_result",
        ["stylebook_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_stylebook_cleanup_check_result_stylebook_id",
        table_name="stylebook_cleanup_check_result",
    )
    op.drop_index(
        "ix_stylebook_cleanup_check_result_run_id",
        table_name="stylebook_cleanup_check_result",
    )
    op.drop_index(
        "ix_stylebook_cleanup_check_result_stylebook_check",
        table_name="stylebook_cleanup_check_result",
    )
    op.drop_index(
        "ix_stylebook_cleanup_check_result_run_ordinal",
        table_name="stylebook_cleanup_check_result",
    )
    op.drop_table("stylebook_cleanup_check_result")

    op.drop_index(
        "ix_stylebook_cleanup_check_run_created_by_user_id",
        table_name="stylebook_cleanup_check_run",
    )
    op.drop_index(
        "ix_stylebook_cleanup_check_run_stylebook_id",
        table_name="stylebook_cleanup_check_run",
    )
    op.drop_index(
        "ix_stylebook_cleanup_check_run_latest",
        table_name="stylebook_cleanup_check_run",
    )
    op.drop_index(
        "ix_stylebook_cleanup_check_run_lookup",
        table_name="stylebook_cleanup_check_run",
    )
    op.drop_table("stylebook_cleanup_check_run")
