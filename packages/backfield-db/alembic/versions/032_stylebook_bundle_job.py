"""Stylebook full bundle export/import job table."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "032_stylebook_bundle_job"
down_revision: Union[str, None] = "031_ai_prj_ovrd_secret"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stylebook_bundle_job",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("source_stylebook_id", sa.Integer(), nullable=True),
        sa.Column("result_stylebook_id", sa.Integer(), nullable=True),
        sa.Column("s3_bucket", sa.Text(), nullable=True),
        sa.Column("s3_key", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("progress_json", sa.JSON(), nullable=True),
        sa.Column("import_request_json", sa.JSON(), nullable=True),
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
            name="stylebook_bundle_job_created_by_user_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["backfield_organization.id"],
            name="stylebook_bundle_job_organization_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["result_stylebook_id"],
            ["stylebook.id"],
            name="stylebook_bundle_job_result_stylebook_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["source_stylebook_id"],
            ["stylebook.id"],
            name="stylebook_bundle_job_source_stylebook_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_bundle_job_pkey"),
    )
    op.create_index(
        "ix_stylebook_bundle_job_org_status",
        "stylebook_bundle_job",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_bundle_job_created_by_user_id",
        "stylebook_bundle_job",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_bundle_job_source_stylebook_id",
        "stylebook_bundle_job",
        ["source_stylebook_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_bundle_job_result_stylebook_id",
        "stylebook_bundle_job",
        ["result_stylebook_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stylebook_bundle_job_result_stylebook_id", table_name="stylebook_bundle_job")
    op.drop_index("ix_stylebook_bundle_job_source_stylebook_id", table_name="stylebook_bundle_job")
    op.drop_index("ix_stylebook_bundle_job_created_by_user_id", table_name="stylebook_bundle_job")
    op.drop_index("ix_stylebook_bundle_job_org_status", table_name="stylebook_bundle_job")
    op.drop_table("stylebook_bundle_job")
