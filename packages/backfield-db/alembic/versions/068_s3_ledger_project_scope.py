"""Scope S3 ingestion ledger identities to projects."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "068_s3_ledger_project_scope"
down_revision: str | None = "067_s3_ingestion_ledger"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_agate_s3_ingestion_ledger_revision",
        "agate_s3_ingestion_ledger",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_agate_s3_ingestion_ledger_revision",
        "agate_s3_ingestion_ledger",
        ["project_id", "source_id", "logical_item_id", "content_fingerprint"],
    )
    op.drop_index(
        "ix_agate_s3_ingestion_ledger_source_item",
        table_name="agate_s3_ingestion_ledger",
    )
    op.create_index(
        "ix_agate_s3_ingestion_ledger_source_item",
        "agate_s3_ingestion_ledger",
        ["project_id", "source_id", "logical_item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agate_s3_ingestion_ledger_source_item",
        table_name="agate_s3_ingestion_ledger",
    )
    op.create_index(
        "ix_agate_s3_ingestion_ledger_source_item",
        "agate_s3_ingestion_ledger",
        ["source_id", "logical_item_id"],
        unique=False,
    )
    op.drop_constraint(
        "uq_agate_s3_ingestion_ledger_revision",
        "agate_s3_ingestion_ledger",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_agate_s3_ingestion_ledger_revision",
        "agate_s3_ingestion_ledger",
        ["source_id", "logical_item_id", "content_fingerprint"],
    )
