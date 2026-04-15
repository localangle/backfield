"""Seed Default Workspace under Backfield org; attach General project.

Revision ID: 003_def_ws_general (must be <=32 chars for alembic_version.version_num).
Revises: 002_backfield_identity
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "003_def_ws_general"
down_revision: Union[str, None] = "002_backfield_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        text(
            """
            INSERT INTO backfield_workspace (organization_id, name, slug, created_at, updated_at)
            SELECT id, 'Default Workspace', 'default', now(), now()
            FROM backfield_organization
            WHERE slug = 'default'
            ON CONFLICT (organization_id, slug) DO NOTHING
            """
        )
    )
    op.execute(
        text(
            """
            UPDATE backfield_project p
            SET workspace_id = w.id
            FROM backfield_workspace w
            INNER JOIN backfield_organization o ON w.organization_id = o.id
            WHERE o.slug = 'default'
              AND w.slug = 'default'
              AND p.slug = 'general'
              AND p.organization_id = o.id
              AND p.workspace_id IS NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(
        text(
            """
            DELETE FROM backfield_workspace w
            USING backfield_organization o
            WHERE w.organization_id = o.id
              AND o.slug = 'default'
              AND w.slug = 'default'
            """
        )
    )
