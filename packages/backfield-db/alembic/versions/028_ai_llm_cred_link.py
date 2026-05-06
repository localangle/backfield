"""Per-model LiteLLM routes + optional org LLM credential FK."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "028_ai_llm_cred_link"
down_revision: Union[str, None] = "027_org_secret_display_name"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backfield_ai_llm_credential",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("api_base", sa.Text(), nullable=True),
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
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_backfield_ai_llm_cred_org",
        "backfield_ai_llm_credential",
        ["organization_id"],
        unique=False,
    )

    op.add_column(
        "backfield_ai_model_config",
        sa.Column("litellm_model", sa.Text(), nullable=True),
    )
    op.add_column(
        "backfield_ai_model_config",
        sa.Column("llm_credential_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "bf_ai_model_cfg_llm_cred_fkey",
        "backfield_ai_model_config",
        "backfield_ai_llm_credential",
        ["llm_credential_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_backfield_ai_model_cfg_llm_cred",
        "backfield_ai_model_config",
        ["llm_credential_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_bf_ai_model_cfg_llm_cred_id",
        "backfield_ai_model_config",
        ["llm_credential_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_bf_ai_model_cfg_llm_cred_id", "backfield_ai_model_config", type_="unique")
    op.drop_index("ix_backfield_ai_model_cfg_llm_cred", table_name="backfield_ai_model_config")
    op.drop_constraint("bf_ai_model_cfg_llm_cred_fkey", "backfield_ai_model_config", type_="foreignkey")
    op.drop_column("backfield_ai_model_config", "llm_credential_id")
    op.drop_column("backfield_ai_model_config", "litellm_model")
    op.drop_index("ix_backfield_ai_llm_cred_org", table_name="backfield_ai_llm_credential")
    op.drop_table("backfield_ai_llm_credential")
