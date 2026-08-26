"""Track how connection evidence currentness was reviewed."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "080_conn_currentness_review"
down_revision: str | None = "079_connection_currentness"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stylebook_connection_evidence",
        sa.Column(
            "currentness_review_source",
            sa.Text(),
            nullable=False,
            server_default="unreviewed",
        ),
    )
    op.create_check_constraint(
        "ck_stylebook_conn_evidence_review_source",
        "stylebook_connection_evidence",
        "currentness_review_source IN "
        "('unreviewed', 'llm', 'manual', 'deterministic')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_stylebook_conn_evidence_review_source",
        "stylebook_connection_evidence",
        type_="check",
    )
    op.drop_column(
        "stylebook_connection_evidence",
        "currentness_review_source",
    )
