"""Add stylebook_connections.description; make nature nullable with null-safe dedupe."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "061_sb_conn_description"
down_revision: Union[str, None] = "060_agate_graph_public_run"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("stylebook_connections")}

    if "description" not in columns:
        op.add_column(
            "stylebook_connections",
            sa.Column("description", sa.Text(), nullable=True),
        )

    op.alter_column(
        "stylebook_connections",
        "nature",
        existing_type=sa.Text(),
        nullable=True,
    )

    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                UPDATE stylebook_connections
                SET description = COALESCE(
                    NULLIF(trim(evidence_json->>'reason'), ''),
                    initcap(replace(nature, '_', ' '))
                )
                WHERE description IS NULL OR trim(description) = ''
                """
            )
        )
    else:
        op.execute(
            sa.text(
                """
                UPDATE stylebook_connections
                SET description = nature
                WHERE description IS NULL OR trim(description) = ''
                """
            )
        )

    existing = {c["name"] for c in inspector.get_unique_constraints("stylebook_connections")}
    if "uq_stylebook_connection_exact_edge" in existing:
        op.drop_constraint(
            "uq_stylebook_connection_exact_edge",
            "stylebook_connections",
            type_="unique",
        )

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DELETE FROM stylebook_connections AS dup
            USING stylebook_connections AS keep
            WHERE dup.id > keep.id
              AND dup.project_id = keep.project_id
              AND dup.from_entity_type = keep.from_entity_type
              AND dup.from_entity_id = keep.from_entity_id
              AND dup.to_entity_type = keep.to_entity_type
              AND dup.to_entity_id = keep.to_entity_id
              AND coalesce(dup.nature, '') = coalesce(keep.nature, '')
              AND coalesce(dup.description, '') = coalesce(keep.description, '')
            """
        )
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_stylebook_connection_exact_edge
            ON stylebook_connections (
                project_id,
                from_entity_type,
                from_entity_id,
                to_entity_type,
                to_entity_id,
                coalesce(nature, ''),
                coalesce(description, '')
            )
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS uq_stylebook_connection_exact_edge")

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

    op.alter_column(
        "stylebook_connections",
        "nature",
        existing_type=sa.Text(),
        nullable=False,
    )

    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("stylebook_connections")}
    if "description" in columns:
        op.drop_column("stylebook_connections", "description")
