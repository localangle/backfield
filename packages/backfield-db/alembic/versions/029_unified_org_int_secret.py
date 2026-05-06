"""Merge custom LLM credentials into organization integration secrets."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "029_unified_org_int_secret"
down_revision: Union[str, None] = "028_ai_llm_cred_link"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "backfield_organization_integration_secret",
        sa.Column("api_base", sa.Text(), nullable=True),
    )

    op.add_column(
        "backfield_ai_model_config",
        sa.Column("integration_secret_id", sa.Integer(), nullable=True),
    )

    conn = op.get_bind()

    cred_rows = conn.execute(
        sa.text(
            "SELECT id, organization_id, label, api_base, value_encrypted, "
            "created_at, updated_at FROM backfield_ai_llm_credential"
        )
    ).mappings().all()

    old_to_new: dict[str, int] = {}
    for r in cred_rows:
        old_id = str(r["id"])
        ik = f"ai.credential.{old_id}"
        result = conn.execute(
            sa.text(
                "INSERT INTO backfield_organization_integration_secret "
                "(organization_id, integration_key, credential_display_name, api_base, "
                "value_encrypted, created_at, updated_at) "
                "VALUES (:organization_id, :integration_key, :credential_display_name, "
                ":api_base, :value_encrypted, :created_at, :updated_at) RETURNING id"
            ),
            {
                "organization_id": int(r["organization_id"]),
                "integration_key": ik,
                "credential_display_name": r["label"],
                "api_base": r["api_base"],
                "value_encrypted": r["value_encrypted"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            },
        )
        old_to_new[old_id] = int(result.scalar_one())

    for old_id, new_id in old_to_new.items():
        conn.execute(
            sa.text(
                "UPDATE backfield_ai_model_config SET integration_secret_id = :nid "
                "WHERE llm_credential_id = :oid"
            ),
            {"nid": new_id, "oid": old_id},
        )

    op.drop_constraint("uq_bf_ai_model_cfg_llm_cred_id", "backfield_ai_model_config", type_="unique")
    op.drop_index("ix_backfield_ai_model_cfg_llm_cred", table_name="backfield_ai_model_config")
    op.drop_constraint("bf_ai_model_cfg_llm_cred_fkey", "backfield_ai_model_config", type_="foreignkey")
    op.drop_column("backfield_ai_model_config", "llm_credential_id")

    op.drop_index("ix_backfield_ai_llm_cred_org", table_name="backfield_ai_llm_credential")
    op.drop_table("backfield_ai_llm_credential")

    op.create_foreign_key(
        "bf_ai_model_integration_secret_fkey",
        "backfield_ai_model_config",
        "backfield_organization_integration_secret",
        ["integration_secret_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_bf_ai_model_integration_secret",
        "backfield_ai_model_config",
        ["integration_secret_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_bf_ai_model_integration_secret_id",
        "backfield_ai_model_config",
        ["integration_secret_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_bf_ai_model_integration_secret_id", "backfield_ai_model_config", type_="unique")
    op.drop_index("ix_bf_ai_model_integration_secret", table_name="backfield_ai_model_config")
    op.drop_constraint("bf_ai_model_integration_secret_fkey", "backfield_ai_model_config", type_="foreignkey")
    op.drop_column("backfield_ai_model_config", "integration_secret_id")

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

    op.drop_column("backfield_organization_integration_secret", "api_base")
