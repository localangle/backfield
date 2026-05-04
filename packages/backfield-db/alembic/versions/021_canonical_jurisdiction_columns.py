"""Structured jurisdiction fields on stylebook_location_canonical.

Revision id must fit ``alembic_version.version_num`` (varchar(32)).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "021_sb_canon_jurisdiction"
down_revision: Union[str, None] = "020_sub_geocode_router_audit"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stylebook_location_canonical",
        sa.Column("country_code", sa.Text(), nullable=True),
    )
    op.add_column(
        "stylebook_location_canonical",
        sa.Column("subdivision_code", sa.Text(), nullable=True),
    )
    op.add_column(
        "stylebook_location_canonical",
        sa.Column("city_name", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_stylebook_location_canonical_country_subdivision",
        "stylebook_location_canonical",
        ["country_code", "subdivision_code"],
        unique=False,
    )
    op.create_index(
        "ix_stylebook_location_canonical_city_name",
        "stylebook_location_canonical",
        ["city_name"],
        unique=False,
    )

    bind = op.get_bind()
    rows = bind.execute(
        text("SELECT id, label FROM stylebook_location_canonical WHERE label IS NOT NULL")
    ).fetchall()
    for rid, label in rows:
        if not label or not isinstance(label, str):
            continue
        parts = [p.strip() for p in label.split(",") if p.strip()]
        if len(parts) < 2:
            continue
        country_code: str | None = None
        subdivision_code: str | None = None
        last = parts[-1].upper()
        if last in ("US", "USA", "UNITED STATES"):
            country_code = "US"
            parts = parts[:-1]
        if parts:
            cand = parts[-1].upper().replace(".", "")
            if len(cand) == 2 and cand.isalpha():
                subdivision_code = cand
        if country_code is None and subdivision_code is None:
            continue
        bind.execute(
            text(
                "UPDATE stylebook_location_canonical SET "
                "country_code = COALESCE(:cc, country_code), "
                "subdivision_code = COALESCE(:sc, subdivision_code) "
                "WHERE id = :id"
            ),
            {"id": str(rid), "cc": country_code, "sc": subdivision_code},
        )


def downgrade() -> None:
    op.drop_index(
        "ix_stylebook_location_canonical_city_name",
        table_name="stylebook_location_canonical",
    )
    op.drop_index(
        "ix_stylebook_location_canonical_country_subdivision",
        table_name="stylebook_location_canonical",
    )
    op.drop_column("stylebook_location_canonical", "city_name")
    op.drop_column("stylebook_location_canonical", "subdivision_code")
    op.drop_column("stylebook_location_canonical", "country_code")
