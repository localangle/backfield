"""Public read performance indexes for geo search and article meta filters."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "049_public_read_perf_indexes"
down_revision: Union[str, None] = "048_location_h3"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_substrate_article_meta_type_category",
        "substrate_article_meta",
        ["meta_type", "category"],
    )

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_substrate_location_geometry_geography_gist
        ON substrate_location
        USING gist ((geometry::geography))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_stylebook_location_canonical_geometry_geography_gist
        ON stylebook_location_canonical
        USING gist ((geometry::geography))
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS idx_stylebook_location_canonical_geometry_geography_gist")
        op.execute("DROP INDEX IF EXISTS idx_substrate_location_geometry_geography_gist")

    op.drop_index(
        "ix_substrate_article_meta_type_category",
        table_name="substrate_article_meta",
    )
