"""Set-null article FK on connection evidence and drop redundant indexes."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "081_conn_evidence_fk"
down_revision: str | None = "080_conn_currentness_review"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_stylebook_conn_evidence_article",
        "stylebook_connection_evidence",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_stylebook_conn_evidence_article",
        "stylebook_connection_evidence",
        "substrate_article",
        ["article_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_index(
        "ix_stylebook_connections_currentness",
        table_name="stylebook_connections",
    )
    op.drop_index(
        "ix_stylebook_connection_evidence_connection_id",
        table_name="stylebook_connection_evidence",
    )
    op.drop_index(
        "ix_stylebook_connections_stylebook_id",
        table_name="stylebook_connections",
    )


def downgrade() -> None:
    op.create_index(
        "ix_stylebook_connections_stylebook_id",
        "stylebook_connections",
        ["stylebook_id"],
    )
    op.create_index(
        "ix_stylebook_connection_evidence_connection_id",
        "stylebook_connection_evidence",
        ["connection_id"],
    )
    op.create_index(
        "ix_stylebook_connections_currentness",
        "stylebook_connections",
        ["currentness"],
    )
    op.drop_constraint(
        "fk_stylebook_conn_evidence_article",
        "stylebook_connection_evidence",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_stylebook_conn_evidence_article",
        "stylebook_connection_evidence",
        "substrate_article",
        ["article_id"],
        ["id"],
    )
