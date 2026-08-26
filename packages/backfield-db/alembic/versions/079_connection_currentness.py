"""Add reported currentness to Stylebook connections and evidence."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "079_connection_currentness"
down_revision: str | None = "078_conn_kg_cutover"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stylebook_connection_evidence",
        sa.Column(
            "asserted_currentness",
            sa.Text(),
            nullable=False,
            server_default="unspecified",
        ),
    )
    op.create_check_constraint(
        "ck_stylebook_conn_evidence_currentness",
        "stylebook_connection_evidence",
        "asserted_currentness IN ('current', 'former', 'unspecified')",
    )

    # Evidence time means source/reference time. Article publication dates are
    # authoritative where available; otherwise retain the prior observed value.
    op.execute(
        sa.text(
            """
            UPDATE stylebook_connection_evidence AS evidence
            SET observed_at = (
                SELECT article.pub_date
                FROM substrate_article AS article
                WHERE article.id = evidence.article_id
            )
            WHERE evidence.article_id IS NOT NULL
              AND EXISTS (
                SELECT 1
                FROM substrate_article AS article
                WHERE article.id = evidence.article_id
                  AND article.pub_date IS NOT NULL
              )
            """
        )
    )

    op.add_column(
        "stylebook_connections",
        sa.Column(
            "currentness",
            sa.Text(),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "stylebook_connections",
        sa.Column("currentness_as_of", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "stylebook_connections",
        sa.Column("currentness_evidence_id", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_stylebook_connection_currentness",
        "stylebook_connections",
        "currentness IN ('current', 'former', 'unknown')",
    )
    op.create_foreign_key(
        "fk_stylebook_connection_currentness_evidence",
        "stylebook_connections",
        "stylebook_connection_evidence",
        ["currentness_evidence_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_stylebook_connections_currentness",
        "stylebook_connections",
        ["currentness"],
    )
    op.create_index(
        "ix_stylebook_connection_currentness_evidence",
        "stylebook_connections",
        ["currentness_evidence_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_stylebook_connection_currentness_evidence",
        table_name="stylebook_connections",
    )
    op.drop_index(
        "ix_stylebook_connections_currentness",
        table_name="stylebook_connections",
    )
    op.drop_constraint(
        "fk_stylebook_connection_currentness_evidence",
        "stylebook_connections",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_stylebook_connection_currentness",
        "stylebook_connections",
        type_="check",
    )
    op.drop_column("stylebook_connections", "currentness_evidence_id")
    op.drop_column("stylebook_connections", "currentness_as_of")
    op.drop_column("stylebook_connections", "currentness")

    op.drop_constraint(
        "ck_stylebook_conn_evidence_currentness",
        "stylebook_connection_evidence",
        type_="check",
    )
    op.drop_column("stylebook_connection_evidence", "asserted_currentness")
