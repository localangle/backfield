"""Project AI model override may reference a dedicated integration secret."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "031_project_model_override_secret"
down_revision: Union[str, None] = "030_ai_share_int_secret"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "backfield_ai_project_model_override",
        sa.Column("integration_secret_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "backfield_ai_project_model_override_integration_secret_id_fkey",
        "backfield_ai_project_model_override",
        "backfield_organization_integration_secret",
        ["integration_secret_id"],
        ["id"],
    )
    op.create_index(
        "ix_backfield_ai_override_integration_secret_id",
        "backfield_ai_project_model_override",
        ["integration_secret_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_backfield_ai_override_integration_secret_id",
        table_name="backfield_ai_project_model_override",
    )
    op.drop_constraint(
        "backfield_ai_project_model_override_integration_secret_id_fkey",
        "backfield_ai_project_model_override",
        type_="foreignkey",
    )
    op.drop_column("backfield_ai_project_model_override", "integration_secret_id")
