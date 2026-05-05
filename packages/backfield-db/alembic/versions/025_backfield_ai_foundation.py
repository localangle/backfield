"""Shared AI model configuration and usage tracking tables."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "025_backfield_ai_foundation"
down_revision: Union[str, None] = "024_stylebook_membership"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backfield_ai_model_config",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_model_id", sa.Text(), nullable=False),
        sa.Column(
            "model_kind",
            sa.Text(),
            server_default="generative",
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("input_token_price", sa.Numeric(18, 12), nullable=True),
        sa.Column("output_token_price", sa.Numeric(18, 12), nullable=True),
        sa.Column("currency", sa.Text(), server_default="USD", nullable=False),
        sa.Column("latest_test_status", sa.Text(), nullable=True),
        sa.Column("latest_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_test_error", sa.Text(), nullable=True),
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
            ["organization_id"],
            ["backfield_organization.id"],
            name="backfield_ai_model_config_organization_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="backfield_ai_model_config_pkey"),
        sa.UniqueConstraint(
            "organization_id",
            "name",
            name="uq_backfield_ai_model_config_org_name",
        ),
    )
    op.create_index(
        "ix_backfield_ai_model_config_organization_id",
        "backfield_ai_model_config",
        ["organization_id"],
    )
    op.create_index(
        "ix_backfield_ai_model_config_org_provider_model",
        "backfield_ai_model_config",
        ["organization_id", "provider", "provider_model_id"],
    )
    op.create_index(
        "ix_backfield_ai_model_config_org_status_kind",
        "backfield_ai_model_config",
        ["organization_id", "status", "model_kind"],
    )

    op.create_table(
        "backfield_ai_project_model_override",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("model_config_id", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
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
            ["model_config_id"],
            ["backfield_ai_model_config.id"],
            name="backfield_ai_project_model_override_model_config_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="backfield_ai_project_model_override_project_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="backfield_ai_project_model_override_pkey"),
        sa.UniqueConstraint(
            "project_id",
            "model_config_id",
            name="uq_backfield_ai_project_model_override_project_model",
        ),
    )
    op.create_index(
        "ix_backfield_ai_project_model_override_model_config_id",
        "backfield_ai_project_model_override",
        ["model_config_id"],
    )
    op.create_index(
        "ix_backfield_ai_project_model_override_project_id",
        "backfield_ai_project_model_override",
        ["project_id"],
    )
    op.create_index(
        "ix_backfield_ai_project_model_override_project_enabled",
        "backfield_ai_project_model_override",
        ["project_id", "enabled"],
    )

    op.create_table(
        "backfield_ai_default_model_role",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("model_config_id", sa.String(), nullable=False),
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
        sa.CheckConstraint(
            "(organization_id IS NOT NULL AND project_id IS NULL) "
            "OR (organization_id IS NULL AND project_id IS NOT NULL)",
            name="ck_backfield_ai_default_model_role_one_scope",
        ),
        sa.ForeignKeyConstraint(
            ["model_config_id"],
            ["backfield_ai_model_config.id"],
            name="backfield_ai_default_model_role_model_config_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["backfield_organization.id"],
            name="backfield_ai_default_model_role_organization_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="backfield_ai_default_model_role_project_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="backfield_ai_default_model_role_pkey"),
    )
    op.create_index(
        "ix_backfield_ai_default_model_role_model_config_id",
        "backfield_ai_default_model_role",
        ["model_config_id"],
    )
    op.create_index(
        "ix_backfield_ai_default_model_role_organization_id",
        "backfield_ai_default_model_role",
        ["organization_id"],
    )
    op.create_index(
        "ix_backfield_ai_default_model_role_project_id",
        "backfield_ai_default_model_role",
        ["project_id"],
    )
    op.create_index(
        "uq_backfield_ai_default_model_role_org_role",
        "backfield_ai_default_model_role",
        ["organization_id", "role"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL AND project_id IS NULL"),
        sqlite_where=sa.text("organization_id IS NOT NULL AND project_id IS NULL"),
    )
    op.create_index(
        "uq_backfield_ai_default_model_role_project_role",
        "backfield_ai_default_model_role",
        ["project_id", "role"],
        unique=True,
        postgresql_where=sa.text("project_id IS NOT NULL AND organization_id IS NULL"),
        sqlite_where=sa.text("project_id IS NOT NULL AND organization_id IS NULL"),
    )

    op.create_table(
        "backfield_ai_call_record",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("processed_item_id", sa.Integer(), nullable=True),
        sa.Column("node_id", sa.Text(), nullable=True),
        sa.Column("node_type", sa.Text(), nullable=True),
        sa.Column("model_config_id", sa.String(), nullable=True),
        sa.Column("model_config_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_model_id", sa.Text(), nullable=False),
        sa.Column(
            "model_kind",
            sa.Text(),
            server_default="generative",
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(18, 12), nullable=True),
        sa.Column("currency", sa.Text(), server_default="USD", nullable=False),
        sa.Column("cost_estimate_source", sa.Text(), nullable=True),
        sa.Column(
            "cost_estimate_incomplete",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("provider_request_id", sa.Text(), nullable=True),
        sa.Column("error_type", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_config_id"],
            ["backfield_ai_model_config.id"],
            name="backfield_ai_call_record_model_config_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["processed_item_id"],
            ["agate_processed_item.id"],
            name="backfield_ai_call_record_processed_item_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="backfield_ai_call_record_project_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agate_run.id"],
            name="backfield_ai_call_record_run_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="backfield_ai_call_record_pkey"),
    )
    op.create_index(
        "ix_backfield_ai_call_record_model_config_id",
        "backfield_ai_call_record",
        ["model_config_id"],
    )
    op.create_index(
        "ix_backfield_ai_call_record_model_status",
        "backfield_ai_call_record",
        ["model_config_id", "status"],
    )
    op.create_index(
        "ix_backfield_ai_call_record_processed_item_id",
        "backfield_ai_call_record",
        ["processed_item_id"],
    )
    op.create_index(
        "ix_backfield_ai_call_record_project_created",
        "backfield_ai_call_record",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_backfield_ai_call_record_project_id",
        "backfield_ai_call_record",
        ["project_id"],
    )
    op.create_index(
        "ix_backfield_ai_call_record_run_id",
        "backfield_ai_call_record",
        ["run_id"],
    )
    op.create_index(
        "ix_backfield_ai_call_record_run_node",
        "backfield_ai_call_record",
        ["run_id", "node_id"],
    )
    op.create_index(
        "ix_backfield_ai_call_record_run_status",
        "backfield_ai_call_record",
        ["run_id", "status"],
    )
    op.create_index(
        "ix_backfield_ai_call_record_status",
        "backfield_ai_call_record",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_backfield_ai_call_record_status", table_name="backfield_ai_call_record")
    op.drop_index("ix_backfield_ai_call_record_run_status", table_name="backfield_ai_call_record")
    op.drop_index("ix_backfield_ai_call_record_run_node", table_name="backfield_ai_call_record")
    op.drop_index("ix_backfield_ai_call_record_run_id", table_name="backfield_ai_call_record")
    op.drop_index("ix_backfield_ai_call_record_project_id", table_name="backfield_ai_call_record")
    op.drop_index(
        "ix_backfield_ai_call_record_project_created",
        table_name="backfield_ai_call_record",
    )
    op.drop_index(
        "ix_backfield_ai_call_record_processed_item_id",
        table_name="backfield_ai_call_record",
    )
    op.drop_index(
        "ix_backfield_ai_call_record_model_status",
        table_name="backfield_ai_call_record",
    )
    op.drop_index(
        "ix_backfield_ai_call_record_model_config_id",
        table_name="backfield_ai_call_record",
    )
    op.drop_table("backfield_ai_call_record")

    op.drop_index(
        "uq_backfield_ai_default_model_role_project_role",
        table_name="backfield_ai_default_model_role",
    )
    op.drop_index(
        "uq_backfield_ai_default_model_role_org_role",
        table_name="backfield_ai_default_model_role",
    )
    op.drop_index(
        "ix_backfield_ai_default_model_role_project_id",
        table_name="backfield_ai_default_model_role",
    )
    op.drop_index(
        "ix_backfield_ai_default_model_role_organization_id",
        table_name="backfield_ai_default_model_role",
    )
    op.drop_index(
        "ix_backfield_ai_default_model_role_model_config_id",
        table_name="backfield_ai_default_model_role",
    )
    op.drop_table("backfield_ai_default_model_role")

    op.drop_index(
        "ix_backfield_ai_project_model_override_project_enabled",
        table_name="backfield_ai_project_model_override",
    )
    op.drop_index(
        "ix_backfield_ai_project_model_override_project_id",
        table_name="backfield_ai_project_model_override",
    )
    op.drop_index(
        "ix_backfield_ai_project_model_override_model_config_id",
        table_name="backfield_ai_project_model_override",
    )
    op.drop_table("backfield_ai_project_model_override")

    op.drop_index(
        "ix_backfield_ai_model_config_org_status_kind",
        table_name="backfield_ai_model_config",
    )
    op.drop_index(
        "ix_backfield_ai_model_config_org_provider_model",
        table_name="backfield_ai_model_config",
    )
    op.drop_index(
        "ix_backfield_ai_model_config_organization_id",
        table_name="backfield_ai_model_config",
    )
    op.drop_table("backfield_ai_model_config")
