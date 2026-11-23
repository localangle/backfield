"""Add cleanup runs, the action ledger, and canonical redirects (`merged_into`)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "084_cleanup_run_ledger"
down_revision: str | None = "083_article_headline_url_fts"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stylebook_cleanup_run",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("client_run_ref", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("credential_id", sa.Integer(), nullable=True),
        sa.Column("credential_label", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["stylebook_id"], ["stylebook.id"], name="stylebook_cleanup_run_stylebook_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["credential_id"],
            ["backfield_api_credential.id"],
            name="stylebook_cleanup_run_credential_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_cleanup_run_pkey"),
    )
    op.create_index(
        "ix_stylebook_cleanup_run_stylebook_id", "stylebook_cleanup_run", ["stylebook_id"]
    )
    op.create_index(
        "ix_stylebook_cleanup_run_credential_id", "stylebook_cleanup_run", ["credential_id"]
    )
    op.create_index(
        "ix_stylebook_cleanup_run_stylebook_status",
        "stylebook_cleanup_run",
        ["stylebook_id", "status"],
    )

    op.create_table(
        "stylebook_cleanup_action",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("canonical_id", sa.Text(), nullable=False),
        sa.Column("related_canonical_id", sa.Text(), nullable=True),
        sa.Column("client_item_id", sa.Text(), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=True),
        sa.Column("credential_id", sa.Integer(), nullable=True),
        sa.Column("credential_label", sa.Text(), nullable=True),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("before_state_json", sa.JSON(), nullable=False),
        sa.Column("reindex_queued", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["stylebook_cleanup_run.id"], name="stylebook_cleanup_action_run_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_id"], ["stylebook.id"], name="stylebook_cleanup_action_stylebook_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["credential_id"],
            ["backfield_api_credential.id"],
            name="stylebook_cleanup_action_credential_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_cleanup_action_pkey"),
    )
    op.create_index(
        "ix_stylebook_cleanup_action_run_created",
        "stylebook_cleanup_action",
        ["run_id", "created_at"],
    )
    op.create_index(
        "ix_stylebook_cleanup_action_stylebook_created",
        "stylebook_cleanup_action",
        ["stylebook_id", "created_at"],
    )
    op.create_index(
        "ix_stylebook_cleanup_action_subject",
        "stylebook_cleanup_action",
        ["stylebook_id", "entity_type", "canonical_id"],
    )

    op.create_table(
        "stylebook_canonical_redirect",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("old_id", sa.Text(), nullable=False),
        sa.Column("new_id", sa.Text(), nullable=False),
        sa.Column("action_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_id"],
            ["stylebook.id"],
            name="stylebook_canonical_redirect_stylebook_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["stylebook_cleanup_action.id"],
            name="stylebook_canonical_redirect_action_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_canonical_redirect_pkey"),
        sa.UniqueConstraint(
            "stylebook_id", "entity_type", "old_id", name="uq_stylebook_canonical_redirect_old"
        ),
    )
    op.create_index(
        "ix_stylebook_canonical_redirect_new",
        "stylebook_canonical_redirect",
        ["stylebook_id", "entity_type", "new_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_stylebook_canonical_redirect_new", table_name="stylebook_canonical_redirect")
    op.drop_table("stylebook_canonical_redirect")
    op.drop_index("ix_stylebook_cleanup_action_subject", table_name="stylebook_cleanup_action")
    op.drop_index(
        "ix_stylebook_cleanup_action_stylebook_created", table_name="stylebook_cleanup_action"
    )
    op.drop_index("ix_stylebook_cleanup_action_run_created", table_name="stylebook_cleanup_action")
    op.drop_table("stylebook_cleanup_action")
    op.drop_index("ix_stylebook_cleanup_run_stylebook_status", table_name="stylebook_cleanup_run")
    op.drop_index("ix_stylebook_cleanup_run_credential_id", table_name="stylebook_cleanup_run")
    op.drop_index("ix_stylebook_cleanup_run_stylebook_id", table_name="stylebook_cleanup_run")
    op.drop_table("stylebook_cleanup_run")
