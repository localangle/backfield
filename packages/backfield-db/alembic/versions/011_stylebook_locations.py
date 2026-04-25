"""Stylebook catalog, workspace link, location canonical + alias tables.

Per-organization Stylebooks; each workspace references exactly one Stylebook.
Default Stylebook per org is backfilled; workspace.stylebook_id is NOT NULL.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_stylebook_locations"
down_revision: Union[str, None] = "010_drop_parent_ids_json"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stylebook",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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
            name="stylebook_organization_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_pkey"),
        sa.UniqueConstraint(
            "organization_id",
            "slug",
            name="uq_stylebook_organization_slug",
        ),
    )
    op.create_index("ix_stylebook_organization_id", "stylebook", ["organization_id"])
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            "uq_stylebook_org_one_default",
            "stylebook",
            ["organization_id"],
            unique=True,
            postgresql_where=sa.text("is_default = true"),
        )

    op.create_table(
        "stylebook_location_canonical",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("primary_substrate_location_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
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
            ["stylebook_id"],
            ["stylebook.id"],
            name="stylebook_location_canonical_stylebook_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["primary_substrate_location_id"],
            ["substrate_location.id"],
            name="stylebook_location_canonical_primary_substrate_location_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_location_canonical_pkey"),
    )
    op.create_index(
        "ix_stylebook_location_canonical_stylebook_id",
        "stylebook_location_canonical",
        ["stylebook_id"],
    )
    op.create_index(
        "ix_stylebook_location_canonical_primary_substrate_location_id",
        "stylebook_location_canonical",
        ["primary_substrate_location_id"],
    )

    op.create_table(
        "stylebook_location_alias",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("location_canonical_id", sa.Integer(), nullable=False),
        sa.Column("alias_text", sa.Text(), nullable=False),
        sa.Column("normalized_alias", sa.Text(), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.Column(
            "suppressed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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
            ["location_canonical_id"],
            ["stylebook_location_canonical.id"],
            name="stylebook_location_alias_location_canonical_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_location_alias_pkey"),
        sa.UniqueConstraint(
            "location_canonical_id",
            "normalized_alias",
            name="uq_stylebook_location_alias_canonical_normalized",
        ),
    )
    op.create_index(
        "ix_stylebook_location_alias_normalized",
        "stylebook_location_alias",
        ["normalized_alias"],
    )

    op.add_column(
        "backfield_workspace",
        sa.Column("stylebook_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "backfield_workspace_stylebook_id_fkey",
        "backfield_workspace",
        "stylebook",
        ["stylebook_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_backfield_workspace_stylebook_id",
        "backfield_workspace",
        ["stylebook_id"],
    )

    # One default Stylebook per organization + link all workspaces in that org.
    conn = op.get_bind()
    org_rows = conn.execute(sa.text("SELECT id FROM backfield_organization")).fetchall()
    for org_row in org_rows:
        org_id = int(org_row[0])
        conn.execute(
            sa.text(
                """
                INSERT INTO stylebook (organization_id, slug, name, is_default)
                VALUES (:oid, 'default', 'Default Stylebook', true)
                """
            ),
            {"oid": org_id},
        )
        row = conn.execute(
            sa.text(
                "SELECT id FROM stylebook WHERE organization_id = :oid AND slug = 'default'"
            ),
            {"oid": org_id},
        ).fetchone()
        if row is None:
            continue
        sb_id = int(row[0])
        conn.execute(
            sa.text(
                """
                UPDATE backfield_workspace
                SET stylebook_id = :sb
                WHERE organization_id = :oid AND stylebook_id IS NULL
                """
            ),
            {"sb": sb_id, "oid": org_id},
        )

    op.alter_column(
        "backfield_workspace",
        "stylebook_id",
        existing_type=sa.Integer(),
        nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("ix_backfield_workspace_stylebook_id", table_name="backfield_workspace")
    op.drop_constraint(
        "backfield_workspace_stylebook_id_fkey",
        "backfield_workspace",
        type_="foreignkey",
    )
    op.drop_column("backfield_workspace", "stylebook_id")

    op.drop_index("ix_stylebook_location_alias_normalized", table_name="stylebook_location_alias")
    op.drop_table("stylebook_location_alias")

    op.drop_index(
        "ix_stylebook_location_canonical_primary_substrate_location_id",
        table_name="stylebook_location_canonical",
    )
    op.drop_index(
        "ix_stylebook_location_canonical_stylebook_id",
        table_name="stylebook_location_canonical",
    )
    op.drop_table("stylebook_location_canonical")

    if bind.dialect.name == "postgresql":
        op.drop_index("uq_stylebook_org_one_default", table_name="stylebook")
    op.drop_index("ix_stylebook_organization_id", table_name="stylebook")
    op.drop_table("stylebook")
