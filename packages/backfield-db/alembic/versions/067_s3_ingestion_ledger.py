"""Add S3 ingestion ledger and processed-item link."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "067_s3_ingestion_ledger"
down_revision: str | None = "066_agate_pi_run_status"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agate_s3_ingestion_ledger",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("logical_item_id", sa.Text(), nullable=False),
        sa.Column("bucket", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("version_id", sa.Text(), nullable=True),
        sa.Column("content_fingerprint", sa.Text(), nullable=False),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("last_modified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("claim_token", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("flow_run_id", sa.Text(), nullable=True),
        sa.Column("processed_item_id", sa.Integer(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="agate_s3_ingestion_ledger_project_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["flow_run_id"],
            ["agate_run.id"],
            name="agate_s3_ingestion_ledger_flow_run_id_fkey",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["processed_item_id"],
            ["agate_processed_item.id"],
            name="agate_s3_ingestion_ledger_processed_item_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="agate_s3_ingestion_ledger_pkey"),
        sa.UniqueConstraint(
            "source_id",
            "logical_item_id",
            "content_fingerprint",
            name="uq_agate_s3_ingestion_ledger_revision",
        ),
    )
    op.create_index(
        "ix_agate_s3_ingestion_ledger_source_item",
        "agate_s3_ingestion_ledger",
        ["source_id", "logical_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_agate_s3_ingestion_ledger_status_lease",
        "agate_s3_ingestion_ledger",
        ["status", "lease_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_agate_s3_ingestion_ledger_project",
        "agate_s3_ingestion_ledger",
        ["project_id"],
        unique=False,
    )

    op.add_column(
        "agate_processed_item",
        sa.Column("ingestion_ledger_id", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "agate_processed_item_ingestion_ledger_id_fkey",
        "agate_processed_item",
        "agate_s3_ingestion_ledger",
        ["ingestion_ledger_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agate_processed_item_ingestion_ledger_id",
        "agate_processed_item",
        ["ingestion_ledger_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agate_processed_item_ingestion_ledger_id",
        table_name="agate_processed_item",
    )
    op.drop_constraint(
        "agate_processed_item_ingestion_ledger_id_fkey",
        "agate_processed_item",
        type_="foreignkey",
    )
    op.drop_column("agate_processed_item", "ingestion_ledger_id")

    op.drop_index(
        "ix_agate_s3_ingestion_ledger_project",
        table_name="agate_s3_ingestion_ledger",
    )
    op.drop_index(
        "ix_agate_s3_ingestion_ledger_status_lease",
        table_name="agate_s3_ingestion_ledger",
    )
    op.drop_index(
        "ix_agate_s3_ingestion_ledger_source_item",
        table_name="agate_s3_ingestion_ledger",
    )
    op.drop_table("agate_s3_ingestion_ledger")
