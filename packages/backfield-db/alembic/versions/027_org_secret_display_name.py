"""Optional friendly label on organization integration secrets."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "027_org_secret_display_name"
down_revision: Union[str, None] = "026_org_integration_secret"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "backfield_organization_integration_secret",
        sa.Column("credential_display_name", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("backfield_organization_integration_secret", "credential_display_name")
