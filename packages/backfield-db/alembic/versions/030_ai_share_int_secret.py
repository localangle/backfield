"""Allow multiple catalog models to share one integration secret."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "030_ai_share_int_secret"
down_revision: Union[str, None] = "029_unified_org_int_secret"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_bf_ai_model_integration_secret_id",
        "backfield_ai_model_config",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_bf_ai_model_integration_secret_id",
        "backfield_ai_model_config",
        ["integration_secret_id"],
    )
