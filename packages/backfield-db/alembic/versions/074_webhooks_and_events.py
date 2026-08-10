"""Add run attempts, run output articles, events, and webhook delivery tables."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "074_webhooks_and_events"
down_revision: str | None = "073_org_settings_json"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agate_run",
        sa.Column(
            "execution_attempt",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )

    op.create_table(
        "agate_run_output_article",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("execution_attempt", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("processed_item_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agate_run.id"],
            name="agate_run_output_article_run_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["substrate_article.id"],
            name="agate_run_output_article_article_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["processed_item_id"],
            ["agate_processed_item.id"],
            name="agate_run_output_article_processed_item_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="agate_run_output_article_pkey"),
        sa.UniqueConstraint(
            "run_id",
            "execution_attempt",
            "article_id",
            name="uq_agate_run_output_article_attempt",
        ),
    )
    op.create_index(
        "ix_agate_run_output_article_run_attempt",
        "agate_run_output_article",
        ["run_id", "execution_attempt"],
        unique=False,
    )
    op.create_index(
        "ix_agate_run_output_article_article",
        "agate_run_output_article",
        ["article_id"],
        unique=False,
    )

    op.create_table(
        "backfield_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_uuid", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column(
            "schema_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("graph_id", sa.Text(), nullable=True),
        sa.Column("graph_name", sa.Text(), nullable=True),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("execution_attempt", sa.Integer(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_test",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["backfield_organization.id"],
            name="backfield_event_organization_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="backfield_event_project_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="backfield_event_pkey"),
        sa.UniqueConstraint("event_uuid", name="uq_backfield_event_uuid"),
    )
    op.create_index(
        "ix_backfield_event_project_seq",
        "backfield_event",
        ["project_id", "id"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_event_project_type_seq",
        "backfield_event",
        ["project_id", "event_type", "id"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_event_created_at",
        "backfield_event",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "backfield_webhook_endpoint",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url_encrypted", sa.Text(), nullable=False),
        sa.Column("display_host", sa.Text(), nullable=False),
        sa.Column("signing_secret_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "secret_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pause_reason", sa.Text(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
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
            ["organization_id"],
            ["backfield_organization.id"],
            name="backfield_webhook_endpoint_organization_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="backfield_webhook_endpoint_project_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["backfield_user.id"],
            name="backfield_webhook_endpoint_created_by_user_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="backfield_webhook_endpoint_pkey"),
    )
    op.create_index(
        "ix_backfield_webhook_endpoint_project_status",
        "backfield_webhook_endpoint",
        ["project_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_webhook_endpoint_org",
        "backfield_webhook_endpoint",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "backfield_webhook_subscription",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("endpoint_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("graph_id", sa.Text(), nullable=False),
        sa.Column("outcomes_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["backfield_webhook_endpoint.id"],
            name="backfield_webhook_subscription_endpoint_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["graph_id"],
            ["agate_graph.id"],
            name="backfield_webhook_subscription_graph_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="backfield_webhook_subscription_pkey"),
        sa.UniqueConstraint(
            "endpoint_id",
            "event_type",
            "graph_id",
            name="uq_backfield_webhook_subscription",
        ),
    )
    op.create_index(
        "ix_backfield_webhook_subscription_endpoint_id",
        "backfield_webhook_subscription",
        ["endpoint_id"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_webhook_subscription_graph",
        "backfield_webhook_subscription",
        ["graph_id"],
        unique=False,
    )

    op.create_table(
        "backfield_webhook_delivery",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("endpoint_id", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), server_default="pending", nullable=False),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("failure_category", sa.Text(), nullable=True),
        sa.Column("failure_summary", sa.Text(), nullable=True),
        sa.Column(
            "is_replay",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_test",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("first_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
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
            ["event_id"],
            ["backfield_event.id"],
            name="backfield_webhook_delivery_event_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["backfield_webhook_endpoint.id"],
            name="backfield_webhook_delivery_endpoint_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="backfield_webhook_delivery_pkey"),
    )
    op.create_index(
        "uq_backfield_webhook_delivery_event_endpoint",
        "backfield_webhook_delivery",
        ["event_id", "endpoint_id"],
        unique=True,
        postgresql_where=sa.text("NOT is_replay"),
        sqlite_where=sa.text("NOT is_replay"),
    )
    op.create_index(
        "ix_backfield_webhook_delivery_due",
        "backfield_webhook_delivery",
        ["state", "next_attempt_at"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_webhook_delivery_endpoint_created",
        "backfield_webhook_delivery",
        ["endpoint_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_webhook_delivery_event",
        "backfield_webhook_delivery",
        ["event_id"],
        unique=False,
    )

    op.create_table(
        "backfield_webhook_delivery_attempt",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("delivery_id", sa.Text(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("failure_category", sa.Text(), nullable=True),
        sa.Column("failure_summary", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["delivery_id"],
            ["backfield_webhook_delivery.id"],
            name="backfield_webhook_delivery_attempt_delivery_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="backfield_webhook_delivery_attempt_pkey"),
    )
    op.create_index(
        "ix_backfield_webhook_delivery_attempt_delivery",
        "backfield_webhook_delivery_attempt",
        ["delivery_id", "attempt_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_backfield_webhook_delivery_attempt_delivery",
        table_name="backfield_webhook_delivery_attempt",
    )
    op.drop_table("backfield_webhook_delivery_attempt")

    op.drop_index(
        "ix_backfield_webhook_delivery_event",
        table_name="backfield_webhook_delivery",
    )
    op.drop_index(
        "ix_backfield_webhook_delivery_endpoint_created",
        table_name="backfield_webhook_delivery",
    )
    op.drop_index(
        "ix_backfield_webhook_delivery_due",
        table_name="backfield_webhook_delivery",
    )
    op.drop_index(
        "uq_backfield_webhook_delivery_event_endpoint",
        table_name="backfield_webhook_delivery",
    )
    op.drop_table("backfield_webhook_delivery")

    op.drop_index(
        "ix_backfield_webhook_subscription_graph",
        table_name="backfield_webhook_subscription",
    )
    op.drop_index(
        "ix_backfield_webhook_subscription_endpoint_id",
        table_name="backfield_webhook_subscription",
    )
    op.drop_table("backfield_webhook_subscription")

    op.drop_index(
        "ix_backfield_webhook_endpoint_org",
        table_name="backfield_webhook_endpoint",
    )
    op.drop_index(
        "ix_backfield_webhook_endpoint_project_status",
        table_name="backfield_webhook_endpoint",
    )
    op.drop_table("backfield_webhook_endpoint")

    op.drop_index("ix_backfield_event_created_at", table_name="backfield_event")
    op.drop_index("ix_backfield_event_project_type_seq", table_name="backfield_event")
    op.drop_index("ix_backfield_event_project_seq", table_name="backfield_event")
    op.drop_table("backfield_event")

    op.drop_index(
        "ix_agate_run_output_article_article",
        table_name="agate_run_output_article",
    )
    op.drop_index(
        "ix_agate_run_output_article_run_attempt",
        table_name="agate_run_output_article",
    )
    op.drop_table("agate_run_output_article")

    op.drop_column("agate_run", "execution_attempt")
