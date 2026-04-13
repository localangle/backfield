"""Initial Agate schema (squashed baseline).

Revision ID: 001_agate_baseline
Revises:
Create Date: 2026-04-10

"""

from __future__ import annotations

import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "001_agate_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_TEMPLATE_SPEC = {
    "name": "Geocode pipeline",
    "nodes": [
        {
            "id": "t1",
            "type": "TextInput",
            "params": {"text": "We visited Chicago, IL and Austin, TX."},
            "position": {"x": 0, "y": 0},
        },
        {
            "id": "t2",
            "type": "PlaceExtract",
            "params": {},
            "position": {"x": 220, "y": 0},
        },
        {
            "id": "t3",
            "type": "GeocodeAgent",
            "params": {},
            "position": {"x": 440, "y": 0},
        },
        {
            "id": "t4",
            "type": "Output",
            "params": {},
            "position": {"x": 660, "y": 0},
        },
    ],
    "edges": [
        {"source": "t1", "target": "t2"},
        {"source": "t2", "target": "t3"},
        {"source": "t3", "target": "t4"},
    ],
}


def upgrade() -> None:
    op.create_table(
        "agate_project",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.execute(text("INSERT INTO agate_project (name, slug) VALUES ('General', 'general')"))

    op.create_table(
        "agate_graph",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("spec_json", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["agate_project.id"],
            name="fk_agate_graph_project",
            ondelete="RESTRICT",
        ),
    )

    op.create_table(
        "agate_run",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("graph_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["graph_id"], ["agate_graph.id"]),
    )
    op.create_index("ix_agate_run_graph_id", "agate_run", ["graph_id"], unique=False)

    op.create_table(
        "agate_template",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("spec_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    tid = str(uuid.uuid4())
    bind = op.get_bind()
    bind.execute(
        text(
            "INSERT INTO agate_template (id, name, description, category, spec_json) "
            "VALUES (:id, :name, :description, :category, :spec_json)"
        ),
        {
            "id": tid,
            "name": "Geocode pipeline",
            "description": "Text → places → geocode → output",
            "category": "starter",
            "spec_json": json.dumps(SEED_TEMPLATE_SPEC),
        },
    )

    op.create_table(
        "agate_project_secret",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value_encrypted", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["project_id"], ["agate_project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "key", name="uq_agate_secret_project_key"),
    )
    op.create_index(
        "ix_agate_project_secret_project_id",
        "agate_project_secret",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agate_project_secret_project_id", table_name="agate_project_secret")
    op.drop_table("agate_project_secret")
    op.drop_table("agate_template")
    op.drop_index("ix_agate_run_graph_id", table_name="agate_run")
    op.drop_table("agate_run")
    op.drop_table("agate_graph")
    op.drop_table("agate_project")
