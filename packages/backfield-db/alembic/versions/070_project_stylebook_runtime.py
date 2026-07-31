"""Make project workspace and Stylebook ownership strict."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "070_project_stylebook_runtime"
down_revision: str | None = "069_project_stylebook_ownership"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _validate_project_ownership(conn: Connection) -> None:
    null_row = conn.execute(
        sa.text(
            """
            SELECT id, workspace_id, stylebook_id
            FROM backfield_project
            WHERE workspace_id IS NULL OR stylebook_id IS NULL
            ORDER BY id
            LIMIT 1
            """
        )
    ).fetchone()
    if null_row is not None:
        raise RuntimeError(
            "cannot enforce project tenancy: "
            f"project {int(null_row[0])} has a null workspace_id or stylebook_id"
        )

    invalid_project = conn.execute(
        sa.text(
            """
            SELECT p.id
            FROM backfield_project AS p
            LEFT JOIN backfield_workspace AS w ON w.id = p.workspace_id
            LEFT JOIN stylebook AS s ON s.id = p.stylebook_id
            WHERE w.id IS NULL
               OR s.id IS NULL
               OR w.organization_id <> p.organization_id
               OR s.organization_id <> p.organization_id
            ORDER BY p.id
            LIMIT 1
            """
        )
    ).fetchone()
    if invalid_project is not None:
        raise RuntimeError(
            "cannot enforce project tenancy: "
            f"project {int(invalid_project[0])} has a missing or cross-organization "
            "workspace/Stylebook assignment"
        )

    invalid_workspace = conn.execute(
        sa.text(
            """
            SELECT w.id
            FROM backfield_workspace AS w
            LEFT JOIN stylebook AS s ON s.id = w.stylebook_id
            WHERE s.id IS NULL OR s.organization_id <> w.organization_id
            ORDER BY w.id
            LIMIT 1
            """
        )
    ).fetchone()
    if invalid_workspace is not None:
        raise RuntimeError(
            "cannot enforce project tenancy: "
            f"workspace {int(invalid_workspace[0])} has a missing or "
            "cross-organization Stylebook assignment"
        )


def upgrade() -> None:
    conn = op.get_bind()
    _validate_project_ownership(conn)

    op.alter_column("backfield_project", "workspace_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("backfield_project", "stylebook_id", existing_type=sa.Integer(), nullable=False)

    op.create_unique_constraint(
        "uq_stylebook_organization_id",
        "stylebook",
        ["organization_id", "id"],
    )
    op.create_unique_constraint(
        "uq_backfield_workspace_org_id",
        "backfield_workspace",
        ["organization_id", "id"],
    )
    op.create_foreign_key(
        "fk_backfield_workspace_org_stylebook",
        "backfield_workspace",
        "stylebook",
        ["organization_id", "stylebook_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_backfield_project_org_workspace",
        "backfield_project",
        "backfield_workspace",
        ["organization_id", "workspace_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_backfield_project_org_stylebook",
        "backfield_project",
        "stylebook",
        ["organization_id", "stylebook_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_backfield_project_org_stylebook",
        "backfield_project",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_backfield_project_org_workspace",
        "backfield_project",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_backfield_workspace_org_stylebook",
        "backfield_workspace",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_backfield_workspace_org_id",
        "backfield_workspace",
        type_="unique",
    )
    op.drop_constraint(
        "uq_stylebook_organization_id",
        "stylebook",
        type_="unique",
    )
    op.alter_column("backfield_project", "stylebook_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("backfield_project", "workspace_id", existing_type=sa.Integer(), nullable=True)
