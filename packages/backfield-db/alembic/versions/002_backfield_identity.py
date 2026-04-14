"""Backfield identity tables; rename agate_project to backfield_project.

Revision ID: 002_backfield_identity
Revises: 001_agate_baseline
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "002_backfield_identity"
down_revision: Union[str, None] = "001_agate_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backfield_organization",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_backfield_organization_slug", "backfield_organization", ["slug"], unique=True)

    op.execute(
        text(
            "INSERT INTO backfield_organization (name, slug) VALUES ('Default', 'default')"
        )
    )

    op.create_table(
        "backfield_workspace",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["backfield_organization.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_backfield_workspace_org_slug"),
    )
    op.create_index(
        "ix_backfield_workspace_organization_id",
        "backfield_workspace",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_workspace_slug",
        "backfield_workspace",
        ["slug"],
        unique=False,
    )

    op.create_table(
        "backfield_user",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_backfield_user_email", "backfield_user", ["email"], unique=True)

    op.create_table(
        "backfield_organization_membership",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["backfield_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["backfield_organization.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_backfield_org_member_user_org"),
    )
    op.create_index(
        "ix_backfield_organization_membership_user_id",
        "backfield_organization_membership",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_organization_membership_organization_id",
        "backfield_organization_membership",
        ["organization_id"],
        unique=False,
    )

    op.rename_table("agate_project", "backfield_project")

    op.add_column(
        "backfield_project",
        sa.Column("organization_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "backfield_project",
        sa.Column("workspace_id", sa.Integer(), nullable=True),
    )

    op.execute(
        text(
            "UPDATE backfield_project SET organization_id = "
            "(SELECT id FROM backfield_organization WHERE slug = 'default' LIMIT 1)"
        )
    )
    op.alter_column(
        "backfield_project",
        "organization_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.create_foreign_key(
        "fk_backfield_project_organization",
        "backfield_project",
        "backfield_organization",
        ["organization_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_backfield_project_workspace",
        "backfield_project",
        "backfield_workspace",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_backfield_project_organization_id",
        "backfield_project",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_project_workspace_id",
        "backfield_project",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "backfield_project_membership",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["backfield_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["backfield_project.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "project_id", name="uq_backfield_project_member_user_proj"),
    )
    op.create_index(
        "ix_backfield_project_membership_user_id",
        "backfield_project_membership",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_project_membership_project_id",
        "backfield_project_membership",
        ["project_id"],
        unique=False,
    )

    op.create_table(
        "backfield_api_credential",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("credential_type", sa.Text(), nullable=False),
        sa.Column("key_prefix", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["backfield_project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["backfield_user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("key_prefix", name="uq_backfield_api_cred_prefix"),
    )
    op.create_index(
        "ix_backfield_api_credential_project_id",
        "backfield_api_credential",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_api_credential_user_id",
        "backfield_api_credential",
        ["user_id"],
        unique=False,
    )

    op.rename_table("agate_project_secret", "backfield_project_secret")
    op.execute(
        text("ALTER INDEX ix_agate_project_secret_project_id RENAME TO ix_backfield_project_secret_project_id")
    )
    op.execute(
        text(
            "ALTER TABLE backfield_project_secret RENAME CONSTRAINT "
            "agate_project_secret_project_id_fkey TO fk_backfield_project_secret_project"
        )
    )
    op.execute(
        text(
            "ALTER TABLE backfield_project_secret RENAME CONSTRAINT "
            "uq_agate_secret_project_key TO uq_backfield_secret_project_key"
        )
    )

    op.execute(
        text(
            "ALTER TABLE agate_graph RENAME CONSTRAINT fk_agate_graph_project TO fk_agate_graph_backfield_project"
        )
    )


def downgrade() -> None:
    op.execute(
        text(
            "ALTER TABLE agate_graph RENAME CONSTRAINT fk_agate_graph_backfield_project TO fk_agate_graph_project"
        )
    )

    op.execute(
        text(
            "ALTER TABLE backfield_project_secret RENAME CONSTRAINT "
            "uq_backfield_secret_project_key TO uq_agate_secret_project_key"
        )
    )
    op.execute(
        text(
            "ALTER TABLE backfield_project_secret RENAME CONSTRAINT "
            "fk_backfield_project_secret_project TO agate_project_secret_project_id_fkey"
        )
    )
    op.execute(
        text("ALTER INDEX ix_backfield_project_secret_project_id RENAME TO ix_agate_project_secret_project_id")
    )
    op.rename_table("backfield_project_secret", "agate_project_secret")

    op.drop_index("ix_backfield_api_credential_user_id", table_name="backfield_api_credential")
    op.drop_index("ix_backfield_api_credential_project_id", table_name="backfield_api_credential")
    op.drop_table("backfield_api_credential")

    op.drop_index("ix_backfield_project_membership_project_id", table_name="backfield_project_membership")
    op.drop_index("ix_backfield_project_membership_user_id", table_name="backfield_project_membership")
    op.drop_table("backfield_project_membership")

    op.drop_index("ix_backfield_project_workspace_id", table_name="backfield_project")
    op.drop_index("ix_backfield_project_organization_id", table_name="backfield_project")
    op.drop_constraint("fk_backfield_project_workspace", "backfield_project", type_="foreignkey")
    op.drop_constraint("fk_backfield_project_organization", "backfield_project", type_="foreignkey")
    op.drop_column("backfield_project", "workspace_id")
    op.drop_column("backfield_project", "organization_id")

    op.rename_table("backfield_project", "agate_project")

    op.drop_index(
        "ix_backfield_organization_membership_organization_id",
        table_name="backfield_organization_membership",
    )
    op.drop_index(
        "ix_backfield_organization_membership_user_id",
        table_name="backfield_organization_membership",
    )
    op.drop_table("backfield_organization_membership")

    op.drop_index("ix_backfield_user_email", table_name="backfield_user")
    op.drop_table("backfield_user")

    op.drop_index("ix_backfield_workspace_slug", table_name="backfield_workspace")
    op.drop_index("ix_backfield_workspace_organization_id", table_name="backfield_workspace")
    op.drop_table("backfield_workspace")

    op.drop_index("ix_backfield_organization_slug", table_name="backfield_organization")
    op.drop_table("backfield_organization")
