"""Organization-level encrypted integration secrets (AI provider keys first)."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "026_organization_integration_secret"
down_revision: Union[str, None] = "025_backfield_ai_foundation"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backfield_organization_integration_secret",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("integration_key", sa.Text(), nullable=False),
        sa.Column("value_encrypted", sa.Text(), nullable=False),
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
            name="backfield_organization_integration_secret_organization_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="backfield_organization_integration_secret_pkey"),
        sa.UniqueConstraint(
            "organization_id",
            "integration_key",
            name="uq_backfield_org_integration_secret_org_key",
        ),
    )
    op.create_index(
        "ix_backfield_organization_integration_secret_organization_id",
        "backfield_organization_integration_secret",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_backfield_organization_integration_secret_organization_id",
        table_name="backfield_organization_integration_secret",
    )
    op.drop_table("backfield_organization_integration_secret")
