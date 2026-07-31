"""Add direct project Stylebook ownership and backfill workspace assignments."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "069_project_stylebook_ownership"
down_revision: str | None = "068_s3_ledger_project_scope"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _stylebook_for_orphan_projects(conn: Connection, organization_id: int) -> int:
    rows = conn.execute(
        sa.text(
            """
            SELECT id, is_default
            FROM stylebook
            WHERE organization_id = :organization_id
            ORDER BY id
            """
        ),
        {"organization_id": organization_id},
    ).fetchall()
    defaults = [int(row[0]) for row in rows if bool(row[1])]
    if len(defaults) == 1:
        return defaults[0]
    if len(defaults) > 1:
        raise RuntimeError(
            f"organization {organization_id} has multiple default Stylebooks"
        )
    if len(rows) == 1:
        return int(rows[0][0])
    if not rows:
        raise RuntimeError(
            f"organization {organization_id} has projects but no Stylebook"
        )
    raise RuntimeError(
        f"organization {organization_id} has projects but no default Stylebook"
    )


def _general_workspace_id(
    conn: Connection,
    *,
    organization_id: int,
    stylebook_id: int,
) -> int:
    row = conn.execute(
        sa.text(
            """
            SELECT id, stylebook_id
            FROM backfield_workspace
            WHERE organization_id = :organization_id AND slug = 'general'
            """
        ),
        {"organization_id": organization_id},
    ).fetchone()
    if row is not None:
        if int(row[1]) != stylebook_id:
            raise RuntimeError(
                f"organization {organization_id} General workspace does not use "
                f"Stylebook {stylebook_id}"
            )
        return int(row[0])

    conn.execute(
        sa.text(
            """
            INSERT INTO backfield_workspace (organization_id, stylebook_id, name, slug)
            VALUES (:organization_id, :stylebook_id, 'General', 'general')
            """
        ),
        {
            "organization_id": organization_id,
            "stylebook_id": stylebook_id,
        },
    )
    created = conn.execute(
        sa.text(
            """
            SELECT id
            FROM backfield_workspace
            WHERE organization_id = :organization_id AND slug = 'general'
            """
        ),
        {"organization_id": organization_id},
    ).fetchone()
    if created is None:
        raise RuntimeError(
            f"failed to create General workspace for organization {organization_id}"
        )
    return int(created[0])


def _backfill_project_stylebooks(conn: Connection) -> None:
    invalid = conn.execute(
        sa.text(
            """
            SELECT p.id, p.organization_id, w.organization_id, s.organization_id
            FROM backfield_project AS p
            LEFT JOIN backfield_workspace AS w ON w.id = p.workspace_id
            LEFT JOIN stylebook AS s ON s.id = w.stylebook_id
            WHERE p.workspace_id IS NOT NULL
              AND (
                w.id IS NULL
                OR w.organization_id <> p.organization_id
                OR s.id IS NULL
                OR s.organization_id <> p.organization_id
              )
            ORDER BY p.id
            """
        )
    ).fetchone()
    if invalid is not None:
        raise RuntimeError(
            f"project {int(invalid[0])} has a cross-organization or invalid "
            "workspace/Stylebook relationship"
        )

    conn.execute(
        sa.text(
            """
            UPDATE backfield_project
            SET stylebook_id = (
                SELECT w.stylebook_id
                FROM backfield_workspace AS w
                WHERE w.id = backfield_project.workspace_id
            )
            WHERE workspace_id IS NOT NULL
            """
        )
    )

    orphan_organizations = conn.execute(
        sa.text(
            """
            SELECT DISTINCT organization_id
            FROM backfield_project
            WHERE workspace_id IS NULL
            ORDER BY organization_id
            """
        )
    ).fetchall()
    for row in orphan_organizations:
        organization_id = int(row[0])
        stylebook_id = _stylebook_for_orphan_projects(conn, organization_id)
        workspace_id = _general_workspace_id(
            conn,
            organization_id=organization_id,
            stylebook_id=stylebook_id,
        )
        conn.execute(
            sa.text(
                """
                UPDATE backfield_project
                SET workspace_id = :workspace_id, stylebook_id = :stylebook_id
                WHERE organization_id = :organization_id AND workspace_id IS NULL
                """
            ),
            {
                "organization_id": organization_id,
                "workspace_id": workspace_id,
                "stylebook_id": stylebook_id,
            },
        )

    remaining = conn.execute(
        sa.text(
            """
            SELECT id
            FROM backfield_project
            WHERE workspace_id IS NULL OR stylebook_id IS NULL
            ORDER BY id
            """
        )
    ).fetchone()
    if remaining is not None:
        raise RuntimeError(f"project {int(remaining[0])} could not be backfilled")


def upgrade() -> None:
    op.add_column(
        "backfield_project",
        sa.Column("stylebook_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "backfield_project_stylebook_id_fkey",
        "backfield_project",
        "stylebook",
        ["stylebook_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_backfield_project_stylebook_id",
        "backfield_project",
        ["stylebook_id"],
    )
    _backfill_project_stylebooks(op.get_bind())


def downgrade() -> None:
    op.drop_index(
        "ix_backfield_project_stylebook_id",
        table_name="backfield_project",
    )
    op.drop_constraint(
        "backfield_project_stylebook_id_fkey",
        "backfield_project",
        type_="foreignkey",
    )
    op.drop_column("backfield_project", "stylebook_id")
