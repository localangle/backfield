"""Add event entity/article scope columns and all-flows webhook subscriptions."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision IDs must fit alembic_version.version_num (varchar(32)).
revision: str = "075_event_scopes_all_flows"
down_revision: str | None = "074_webhooks_and_events"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("backfield_event", sa.Column("article_id", sa.Integer(), nullable=True))
    op.add_column("backfield_event", sa.Column("entity_type", sa.Text(), nullable=True))
    op.add_column("backfield_event", sa.Column("entity_id", sa.Text(), nullable=True))

    # NULL graph_id now means "all flows in the endpoint's project".
    op.alter_column(
        "backfield_webhook_subscription",
        "graph_id",
        existing_type=sa.Text(),
        nullable=True,
    )
    # NULL rows escape the composite unique constraint; enforce at most one
    # all-flows row per (endpoint, event type) with a partial unique index.
    op.create_index(
        "uq_backfield_webhook_subscription_all_flows",
        "backfield_webhook_subscription",
        ["endpoint_id", "event_type"],
        unique=True,
        postgresql_where=sa.text("graph_id IS NULL"),
        sqlite_where=sa.text("graph_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_backfield_webhook_subscription_all_flows",
        table_name="backfield_webhook_subscription",
    )
    op.execute("DELETE FROM backfield_webhook_subscription WHERE graph_id IS NULL")
    op.alter_column(
        "backfield_webhook_subscription",
        "graph_id",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_column("backfield_event", "entity_id")
    op.drop_column("backfield_event", "entity_type")
    op.drop_column("backfield_event", "article_id")
