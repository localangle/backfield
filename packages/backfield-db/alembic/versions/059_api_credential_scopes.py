"""Add scopes to backfield_api_credential."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "059_api_credential_scopes"
down_revision: Union[str, None] = "058_sb_candidate_ai_review"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "backfield_api_credential",
        sa.Column("scopes", sa.Text(), nullable=False, server_default="read"),
    )


def downgrade() -> None:
    op.drop_column("backfield_api_credential", "scopes")
