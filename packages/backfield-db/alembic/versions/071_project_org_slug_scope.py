"""Scope project slugs to organizations."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "071_project_org_slug_scope"
down_revision: str | None = "070_project_stylebook_runtime"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _global_slug_constraint_name() -> str:
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints("backfield_project"):
        if constraint.get("column_names") == ["slug"] and constraint.get("name"):
            return str(constraint["name"])
    raise RuntimeError("global backfield_project slug constraint was not found")


def upgrade() -> None:
    op.drop_constraint(
        _global_slug_constraint_name(),
        "backfield_project",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_backfield_project_org_slug",
        "backfield_project",
        ["organization_id", "slug"],
    )
    op.create_index(
        "ix_backfield_project_org_workspace",
        "backfield_project",
        ["organization_id", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_project_org_stylebook",
        "backfield_project",
        ["organization_id", "stylebook_id"],
        unique=False,
    )


def downgrade() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            """
            SELECT slug
            FROM backfield_project
            GROUP BY slug
            HAVING count(*) > 1
            ORDER BY slug
            LIMIT 1
            """
        )
    ).fetchone()
    if duplicate is not None:
        raise RuntimeError(
            "cannot restore global project slug uniqueness: "
            f"slug {str(duplicate[0])!r} exists in several organizations"
        )
    op.drop_index("ix_backfield_project_org_stylebook", table_name="backfield_project")
    op.drop_index("ix_backfield_project_org_workspace", table_name="backfield_project")
    op.drop_constraint(
        "uq_backfield_project_org_slug",
        "backfield_project",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_backfield_project_slug",
        "backfield_project",
        ["slug"],
    )
