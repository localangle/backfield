"""Add Stylebook-scoped connection columns, evidence, and custom natures (Phase A KG)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "077_conn_kg_phase_a"
down_revision: str | None = "076_typed_canonical_meta"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("stylebook_connections")}

    if "stylebook_id" not in columns:
        op.add_column(
            "stylebook_connections",
            sa.Column("stylebook_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_stylebook_connections_stylebook_id",
            "stylebook_connections",
            "stylebook",
            ["stylebook_id"],
            ["id"],
        )
        op.create_index(
            "ix_stylebook_connections_stylebook_id",
            "stylebook_connections",
            ["stylebook_id"],
        )
        op.create_index(
            "ix_stylebook_connection_sb_from",
            "stylebook_connections",
            ["stylebook_id", "from_entity_type", "from_entity_id"],
        )
        op.create_index(
            "ix_stylebook_connection_sb_to",
            "stylebook_connections",
            ["stylebook_id", "to_entity_type", "to_entity_id"],
        )

    if "closed_at" not in columns:
        op.add_column(
            "stylebook_connections",
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "updated_at" not in columns:
        op.add_column(
            "stylebook_connections",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )

    # Backfill stylebook_id from each project's owned Stylebook.
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                UPDATE stylebook_connections AS c
                SET stylebook_id = p.stylebook_id
                FROM backfield_project AS p
                WHERE c.project_id = p.id
                  AND c.stylebook_id IS NULL
                """
            )
        )
    else:
        op.execute(
            sa.text(
                """
                UPDATE stylebook_connections
                SET stylebook_id = (
                    SELECT p.stylebook_id
                    FROM backfield_project AS p
                    WHERE p.id = stylebook_connections.project_id
                )
                WHERE stylebook_id IS NULL
                """
            )
        )

    tables = set(inspector.get_table_names())
    if "stylebook_connection_evidence" not in tables:
        op.create_table(
            "stylebook_connection_evidence",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("connection_id", sa.Integer(), nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("quote", sa.Text(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("source", sa.Text(), nullable=True),
            sa.Column("prompt_version", sa.Text(), nullable=True),
            sa.Column("run_id", sa.Text(), nullable=True),
            sa.Column("processed_item_id", sa.Integer(), nullable=True),
            sa.Column("match_basis", sa.Text(), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("payload_json", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["connection_id"],
                ["stylebook_connections.id"],
                name="fk_stylebook_conn_evidence_connection",
            ),
            sa.ForeignKeyConstraint(
                ["article_id"],
                ["substrate_article.id"],
                name="fk_stylebook_conn_evidence_article",
            ),
        )
        op.create_index(
            "ix_stylebook_conn_evidence_connection",
            "stylebook_connection_evidence",
            ["connection_id", "created_at"],
        )
        op.create_index(
            "ix_stylebook_conn_evidence_article",
            "stylebook_connection_evidence",
            ["article_id"],
        )
        op.create_index(
            "ix_stylebook_connection_evidence_connection_id",
            "stylebook_connection_evidence",
            ["connection_id"],
        )
        # Partial unique: one evidence row per article per connection.
        if bind.dialect.name == "postgresql":
            op.execute(
                """
                CREATE UNIQUE INDEX uq_stylebook_conn_evidence_article
                ON stylebook_connection_evidence (connection_id, article_id)
                WHERE article_id IS NOT NULL
                """
            )

    if "stylebook_connection_nature_custom" not in tables:
        op.create_table(
            "stylebook_connection_nature_custom",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("stylebook_id", sa.Integer(), nullable=False),
            sa.Column("slug", sa.Text(), nullable=False),
            sa.Column("label", sa.Text(), nullable=False),
            sa.Column("equivalent_to", sa.Text(), nullable=True),
            sa.Column(
                "temporal_kind",
                sa.Text(),
                server_default="dynamic",
                nullable=False,
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
                name="fk_stylebook_conn_nature_custom_sb",
            ),
            sa.UniqueConstraint(
                "stylebook_id",
                "slug",
                name="uq_stylebook_connection_nature_custom_slug",
            ),
        )
        op.create_index(
            "ix_stylebook_connection_nature_custom_stylebook_id",
            "stylebook_connection_nature_custom",
            ["stylebook_id"],
        )


def downgrade() -> None:
    op.drop_table("stylebook_connection_nature_custom")
    op.drop_table("stylebook_connection_evidence")
    op.drop_index("ix_stylebook_connection_sb_to", table_name="stylebook_connections")
    op.drop_index("ix_stylebook_connection_sb_from", table_name="stylebook_connections")
    op.drop_index("ix_stylebook_connections_stylebook_id", table_name="stylebook_connections")
    op.drop_constraint(
        "fk_stylebook_connections_stylebook_id",
        "stylebook_connections",
        type_="foreignkey",
    )
    op.drop_column("stylebook_connections", "updated_at")
    op.drop_column("stylebook_connections", "closed_at")
    op.drop_column("stylebook_connections", "stylebook_id")
