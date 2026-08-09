"""Add organization settings_json for tenant preferences (map defaults, etc.)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "073_org_settings_json"
down_revision: str | None = "072_user_password_change_flag"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "backfield_organization",
        sa.Column("settings_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("backfield_organization", "settings_json")
