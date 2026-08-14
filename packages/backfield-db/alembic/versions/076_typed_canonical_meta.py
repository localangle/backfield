"""Replace freeform Stylebook canonical meta JSON with typed scalar columns."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision IDs must fit alembic_version.version_num (varchar(32)).
revision: str = "076_typed_canonical_meta"
down_revision: str | None = "075_event_scopes_all_flows"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_META_TABLES: tuple[tuple[str, str, str], ...] = (
    (
        "stylebook_location_meta",
        "stylebook_location_canonical_id",
        "ix_stylebook_location_meta_canonical_type",
    ),
    (
        "stylebook_person_meta",
        "stylebook_person_canonical_id",
        "ix_stylebook_person_meta_canonical_type",
    ),
    (
        "stylebook_organization_meta",
        "stylebook_organization_canonical_id",
        "ix_stylebook_organization_meta_canonical_type",
    ),
)


def upgrade() -> None:
    for table, canonical_col, old_index in _META_TABLES:
        op.execute(sa.text(f"TRUNCATE TABLE {table}"))
        op.drop_index(old_index, table_name=table)
        op.drop_column(table, "data_json")
        op.drop_column(table, "deleted")
        op.add_column(table, sa.Column("value_type", sa.Text(), nullable=False))
        op.add_column(table, sa.Column("value_text", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("value_number", sa.Numeric(24, 8), nullable=True))
        op.add_column(table, sa.Column("value_boolean", sa.Boolean(), nullable=True))
        op.create_unique_constraint(
            f"uq_{table}_canonical_type",
            table,
            [canonical_col, "meta_type"],
        )
        op.create_index(
            f"ix_{table}_type_text",
            table,
            ["meta_type", "value_text"],
        )
        op.create_index(
            f"ix_{table}_type_number",
            table,
            ["meta_type", "value_number"],
        )
        op.create_check_constraint(
            f"ck_{table}_value_type",
            table,
            "value_type IN ('text', 'number', 'boolean')",
        )


def downgrade() -> None:
    for table, canonical_col, old_index in reversed(_META_TABLES):
        op.execute(sa.text(f"TRUNCATE TABLE {table}"))
        op.drop_constraint(f"ck_{table}_value_type", table, type_="check")
        op.drop_index(f"ix_{table}_type_number", table_name=table)
        op.drop_index(f"ix_{table}_type_text", table_name=table)
        op.drop_constraint(f"uq_{table}_canonical_type", table, type_="unique")
        op.drop_column(table, "value_boolean")
        op.drop_column(table, "value_number")
        op.drop_column(table, "value_text")
        op.drop_column(table, "value_type")
        op.add_column(
            table,
            sa.Column(
                "deleted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        op.add_column(table, sa.Column("data_json", sa.JSON(), nullable=True))
        op.create_index(old_index, table, [canonical_col, "meta_type"])
