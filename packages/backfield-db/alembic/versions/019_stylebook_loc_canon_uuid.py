"""Location canonical UUID (text) PK + slug; polymorphic connection ids as text.

Destructive for Stylebook location catalog rows: drops canonical-linked tables and
recreates them. ``substrate_location.stylebook_location_canonical_id`` is recreated
as TEXT FK. Requires ``make reset-db`` / fresh DB when upgrading from pre-019 data.

Revision id must fit ``alembic_version.version_num`` (varchar(32)).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "019_sb_loc_canon_uuid"
down_revision: Union[str, None] = "018_drop_sb_loc_meta_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    json_type = postgresql.JSONB() if is_pg else sa.JSON()

    op.drop_table("stylebook_connections")
    op.drop_table("stylebook_location_meta")
    if is_pg:
        op.execute(sa.text("DROP INDEX IF EXISTS ix_stylebook_location_alias_norm_trgm"))
    op.drop_table("stylebook_location_alias")

    op.drop_constraint(
        "substrate_location_stylebook_location_canonical_id_fkey",
        "substrate_location",
        type_="foreignkey",
    )
    op.drop_index("ix_substrate_location_project_canonical", table_name="substrate_location")
    if is_pg:
        op.drop_index(
            "ix_substrate_location_project_open_queue",
            table_name="substrate_location",
        )
    op.drop_column("substrate_location", "stylebook_location_canonical_id")

    op.drop_constraint(
        "stylebook_location_canonical_primary_substrate_location_id_fkey",
        "stylebook_location_canonical",
        type_="foreignkey",
    )
    if is_pg:
        op.drop_index(
            "idx_stylebook_location_canonical_geometry_gist",
            table_name="stylebook_location_canonical",
        )
        op.drop_column("stylebook_location_canonical", "geometry")
    else:
        op.drop_column("stylebook_location_canonical", "geometry")

    op.drop_index(
        "ix_stylebook_location_canonical_primary_substrate_location_id",
        table_name="stylebook_location_canonical",
    )
    op.drop_index(
        "ix_stylebook_location_canonical_stylebook_id",
        table_name="stylebook_location_canonical",
    )
    op.drop_table("stylebook_location_canonical")

    id_default = sa.text("gen_random_uuid()::text") if is_pg else None
    op.create_table(
        "stylebook_location_canonical",
        sa.Column("id", sa.Text(), server_default=id_default, nullable=False),
        sa.Column("stylebook_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("location_type", sa.Text(), nullable=True),
        sa.Column("formatted_address", sa.Text(), nullable=True),
        sa.Column("primary_substrate_location_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("geometry_json", json_type, nullable=True),
        sa.Column("geometry_type", sa.Text(), nullable=True),
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
        sa.UniqueConstraint(
            "stylebook_id",
            "slug",
            name="uq_stylebook_location_canonical_stylebook_slug",
        ),
    )
    if is_pg:
        op.add_column(
            "stylebook_location_canonical",
            sa.Column(
                "geometry",
                Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
                nullable=True,
            ),
        )
        op.create_index(
            "idx_stylebook_location_canonical_geometry_gist",
            "stylebook_location_canonical",
            ["geometry"],
            postgresql_using="gist",
        )
    else:
        op.add_column(
            "stylebook_location_canonical",
            sa.Column("geometry", sa.Text(), nullable=True),
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

    op.add_column(
        "substrate_location",
        sa.Column("stylebook_location_canonical_id", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "substrate_location_stylebook_location_canonical_id_fkey",
        "substrate_location",
        "stylebook_location_canonical",
        ["stylebook_location_canonical_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_substrate_location_project_canonical",
        "substrate_location",
        ["project_id", "stylebook_location_canonical_id"],
    )
    if is_pg:
        op.create_index(
            "ix_substrate_location_project_open_queue",
            "substrate_location",
            ["project_id"],
            postgresql_where=sa.text("stylebook_location_canonical_id IS NULL"),
        )

    op.create_table(
        "stylebook_location_alias",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("location_canonical_id", sa.Text(), nullable=False),
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
    if is_pg:
        op.execute(
            sa.text(
                "CREATE INDEX ix_stylebook_location_alias_norm_trgm "
                "ON stylebook_location_alias USING gin (normalized_alias gin_trgm_ops)"
            )
        )

    op.create_table(
        "stylebook_location_meta",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("stylebook_location_canonical_id", sa.Text(), nullable=False),
        sa.Column("meta_type", sa.Text(), nullable=False),
        sa.Column("data_json", json_type, nullable=True),
        sa.Column(
            "added",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "edited",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="stylebook_location_meta_project_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stylebook_location_canonical_id"],
            ["stylebook_location_canonical.id"],
            name="stylebook_location_meta_canonical_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_location_meta_pkey"),
    )
    op.create_index(
        "ix_stylebook_location_meta_canonical_type",
        "stylebook_location_meta",
        ["stylebook_location_canonical_id", "meta_type"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_location_meta_project_id",
        "stylebook_location_meta",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_location_meta_stylebook_location_canonical_id",
        "stylebook_location_meta",
        ["stylebook_location_canonical_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_location_meta_meta_type",
        "stylebook_location_meta",
        ["meta_type"],
        unique=False,
    )

    op.create_table(
        "stylebook_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("from_entity_type", sa.Text(), nullable=False),
        sa.Column("from_entity_id", sa.Text(), nullable=False),
        sa.Column("to_entity_type", sa.Text(), nullable=False),
        sa.Column("to_entity_id", sa.Text(), nullable=False),
        sa.Column("nature", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="stylebook_connections_project_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="stylebook_connections_pkey"),
    )
    op.create_index(
        "ix_stylebook_connection_from",
        "stylebook_connections",
        ["project_id", "from_entity_type", "from_entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_connection_to",
        "stylebook_connections",
        ["project_id", "to_entity_type", "to_entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_connection_nature",
        "stylebook_connections",
        ["project_id", "nature"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_connections_project_id",
        "stylebook_connections",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_connections_from_entity_type",
        "stylebook_connections",
        ["from_entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_connections_to_entity_type",
        "stylebook_connections",
        ["to_entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_connections_from_entity_id",
        "stylebook_connections",
        ["from_entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_connections_to_entity_id",
        "stylebook_connections",
        ["to_entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_connections_nature",
        "stylebook_connections",
        ["nature"],
        unique=False,
    )


def downgrade() -> None:
    raise NotImplementedError(
        "019_sb_loc_canon_uuid is destructive; downgrade to integer canonical ids is not supported."
    )
