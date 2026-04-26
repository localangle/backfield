"""Stylebook location meta + directed connections between canonicals.

Revision id must fit ``alembic_version.version_num`` (varchar(32)).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "017_sb_loc_meta_conn"
down_revision: Union[str, None] = "016_agate_processed_item"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = postgresql.JSONB() if bind.dialect.name == "postgresql" else sa.JSON()

    op.create_table(
        "stylebook_location_meta",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("stylebook_location_canonical_id", sa.Integer(), nullable=False),
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
        sa.Column("from_entity_id", sa.Integer(), nullable=False),
        sa.Column("to_entity_type", sa.Text(), nullable=False),
        sa.Column("to_entity_id", sa.Integer(), nullable=False),
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
    op.drop_index("ix_stylebook_connections_nature", table_name="stylebook_connections")
    op.drop_index("ix_stylebook_connections_to_entity_id", table_name="stylebook_connections")
    op.drop_index("ix_stylebook_connections_from_entity_id", table_name="stylebook_connections")
    op.drop_index("ix_stylebook_connections_to_entity_type", table_name="stylebook_connections")
    op.drop_index("ix_stylebook_connections_from_entity_type", table_name="stylebook_connections")
    op.drop_index("ix_stylebook_connections_project_id", table_name="stylebook_connections")
    op.drop_index("ix_stylebook_connection_nature", table_name="stylebook_connections")
    op.drop_index("ix_stylebook_connection_to", table_name="stylebook_connections")
    op.drop_index("ix_stylebook_connection_from", table_name="stylebook_connections")
    op.drop_table("stylebook_connections")

    op.drop_index("ix_stylebook_location_meta_meta_type", table_name="stylebook_location_meta")
    op.drop_index(
        "ix_stylebook_location_meta_stylebook_location_canonical_id",
        table_name="stylebook_location_meta",
    )
    op.drop_index("ix_stylebook_location_meta_project_id", table_name="stylebook_location_meta")
    op.drop_index("ix_stylebook_location_meta_canonical_type", table_name="stylebook_location_meta")
    op.drop_table("stylebook_location_meta")
