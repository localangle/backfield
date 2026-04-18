"""pg_trgm for alias recall + optional geometry on stylebook_location_canonical.

Postgres: CREATE EXTENSION IF NOT EXISTS pg_trgm (fail if not permitted), GIN index on
``stylebook_location_alias.normalized_alias`` for trigram search.

Revision id must fit ``alembic_version.version_num`` (varchar(32)).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "014_pg_trgm_canon_geom"
down_revision: Union[str, None] = "013_substrate_slc_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        op.execute(
            sa.text(
                "CREATE INDEX ix_stylebook_location_alias_norm_trgm "
                "ON stylebook_location_alias USING gin (normalized_alias gin_trgm_ops)"
            )
        )

    op.add_column(
        "stylebook_location_canonical",
        sa.Column("geometry_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "stylebook_location_canonical",
        sa.Column("geometry_type", sa.Text(), nullable=True),
    )
    if bind.dialect.name == "postgresql":
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


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index(
            "idx_stylebook_location_canonical_geometry_gist",
            table_name="stylebook_location_canonical",
        )
        op.drop_column("stylebook_location_canonical", "geometry")
        op.execute(sa.text("DROP INDEX IF EXISTS ix_stylebook_location_alias_norm_trgm"))
        # Do not DROP EXTENSION pg_trgm; other objects may depend on it in shared DBs.
    else:
        op.drop_column("stylebook_location_canonical", "geometry")

    op.drop_column("stylebook_location_canonical", "geometry_type")
    op.drop_column("stylebook_location_canonical", "geometry_json")
