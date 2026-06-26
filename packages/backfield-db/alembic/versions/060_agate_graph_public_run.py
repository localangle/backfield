"""Add public_run_enabled to agate_graph."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "060_agate_graph_public_run"
down_revision: Union[str, None] = "059_api_credential_scopes"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agate_graph",
        sa.Column("public_run_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("agate_graph", "public_run_enabled")
