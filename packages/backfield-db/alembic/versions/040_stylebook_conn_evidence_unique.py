"""Add stylebook_connections evidence_json and exact-edge uniqueness.

Revision id must fit ``alembic_version.version_num`` (varchar(32)).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "040_sb_conn_evidence"
down_revision: Union[str, None] = "039_organization_schema"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("stylebook_connections")}

    if "evidence_json" not in columns:
        op.add_column(
            "stylebook_connections",
            sa.Column("evidence_json", sa.JSON(), nullable=True),
        )

    # Keep the oldest row when duplicate exact edges exist before the constraint.
    op.execute(
        sa.text(
            """
            DELETE FROM stylebook_connections AS dup
            USING stylebook_connections AS keep
            WHERE dup.id > keep.id
              AND dup.project_id = keep.project_id
              AND dup.from_entity_type = keep.from_entity_type
              AND dup.from_entity_id = keep.from_entity_id
              AND dup.to_entity_type = keep.to_entity_type
              AND dup.to_entity_id = keep.to_entity_id
              AND dup.nature = keep.nature
            """
        )
    )

    existing = {c["name"] for c in inspector.get_unique_constraints("stylebook_connections")}
    if "uq_stylebook_connection_exact_edge" not in existing:
        op.create_unique_constraint(
            "uq_stylebook_connection_exact_edge",
            "stylebook_connections",
            [
                "project_id",
                "from_entity_type",
                "from_entity_id",
                "to_entity_type",
                "to_entity_id",
                "nature",
            ],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_unique_constraints("stylebook_connections")}
    if "uq_stylebook_connection_exact_edge" in existing:
        op.drop_constraint(
            "uq_stylebook_connection_exact_edge",
            "stylebook_connections",
            type_="unique",
        )

    columns = {c["name"] for c in inspector.get_columns("stylebook_connections")}
    if "evidence_json" in columns:
        op.drop_column("stylebook_connections", "evidence_json")
