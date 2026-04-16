"""Align article.source_run_id with AgateRun string ids.

Revision ID: 006_article_source_run_id_text
Revises: 005_location_schema_foundation
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_article_source_run_id_text"
down_revision: Union[str, None] = "005_location_schema_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Older drafts stored an integer here; Backfield `agate_run.id` is a UUID string.
    # Clear legacy values so the FK to `agate_run` can be enforced safely.
    op.execute("UPDATE backfield_article SET source_run_id = NULL")
    op.alter_column(
        "backfield_article",
        "source_run_id",
        existing_type=sa.Integer(),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="source_run_id::text",
    )
    op.create_foreign_key(
        "fk_backfield_article_source_run_id_agate_run",
        "backfield_article",
        "agate_run",
        ["source_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_backfield_article_source_run_id_agate_run", "backfield_article", type_="foreignkey")
    op.alter_column(
        "backfield_article",
        "source_run_id",
        existing_type=sa.Text(),
        type_=sa.Integer(),
        existing_nullable=True,
        postgresql_using="NULLIF(source_run_id, '')::integer",
    )
