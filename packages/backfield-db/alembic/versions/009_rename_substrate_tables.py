"""Rename shared content/location tables from backfield_* to substrate_*.

Revision ID: 009_rename_substrate_tables
Revises: 008_drop_occurrence_context_text
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "009_rename_substrate_tables"
down_revision: Union[str, None] = "008_drop_occurrence_context_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_RENAMES_UP = (
    ("backfield_location_cache", "substrate_location_cache"),
    ("backfield_location_mention_occurrence", "substrate_location_mention_occurrence"),
    ("backfield_image", "substrate_image"),
    ("backfield_location_mention", "substrate_location_mention"),
    ("backfield_location", "substrate_location"),
    ("backfield_article", "substrate_article"),
)

_CONSTRAINT_RENAMES_UP: tuple[tuple[str, str, str], ...] = (
    ("substrate_location_cache", "backfield_location_cache_pkey", "substrate_location_cache_pkey"),
    (
        "substrate_location_cache",
        "uq_backfield_location_cache_project_query",
        "uq_substrate_location_cache_project_query",
    ),
    (
        "substrate_location_cache",
        "backfield_location_cache_project_id_fkey",
        "substrate_location_cache_project_id_fkey",
    ),
    (
        "substrate_location_mention_occurrence",
        "backfield_location_mention_occurrence_pkey",
        "substrate_location_mention_occurrence_pkey",
    ),
    (
        "substrate_location_mention_occurrence",
        "backfield_location_mention_occurrence_location_mention_id_fkey",
        "substrate_location_mention_occurrence_location_mention_id_fkey",
    ),
    ("substrate_image", "backfield_image_pkey", "substrate_image_pkey"),
    ("substrate_image", "uq_backfield_image_article_image_id", "uq_substrate_image_article_image_id"),
    ("substrate_image", "backfield_image_article_id_fkey", "substrate_image_article_id_fkey"),
    ("substrate_location_mention", "backfield_location_mention_pkey", "substrate_location_mention_pkey"),
    (
        "substrate_location_mention",
        "uq_backfield_location_mention_article_location",
        "uq_substrate_location_mention_article_location",
    ),
    (
        "substrate_location_mention",
        "backfield_location_mention_article_id_fkey",
        "substrate_location_mention_article_id_fkey",
    ),
    (
        "substrate_location_mention",
        "backfield_location_mention_location_id_fkey",
        "substrate_location_mention_location_id_fkey",
    ),
    ("substrate_location", "backfield_location_pkey", "substrate_location_pkey"),
    (
        "substrate_location",
        "uq_backfield_location_project_external",
        "uq_substrate_location_project_external",
    ),
    (
        "substrate_location",
        "uq_backfield_location_project_fingerprint",
        "uq_substrate_location_project_fingerprint",
    ),
    ("substrate_location", "backfield_location_project_id_fkey", "substrate_location_project_id_fkey"),
    ("substrate_article", "backfield_article_pkey", "substrate_article_pkey"),
    (
        "substrate_article",
        "uq_backfield_article_project_external",
        "uq_substrate_article_project_external",
    ),
    ("substrate_article", "uq_backfield_article_project_url", "uq_substrate_article_project_url"),
    ("substrate_article", "backfield_article_project_id_fkey", "substrate_article_project_id_fkey"),
    (
        "substrate_article",
        "fk_backfield_article_source_run_id_agate_run",
        "fk_substrate_article_source_run_id_agate_run",
    ),
)

_INDEX_RENAMES_UP: tuple[tuple[str, str], ...] = (
    ("ix_backfield_article_project_id", "ix_substrate_article_project_id"),
    ("ix_backfield_article_url", "ix_substrate_article_url"),
    ("ix_backfield_article_headline", "ix_substrate_article_headline"),
    ("ix_backfield_article_pub_date", "ix_substrate_article_pub_date"),
    ("ix_backfield_article_added", "ix_substrate_article_added"),
    ("ix_backfield_article_edited", "ix_substrate_article_edited"),
    ("ix_backfield_article_deleted", "ix_substrate_article_deleted"),
    ("idx_backfield_article_project_pub_date", "idx_substrate_article_project_pub_date"),
    ("idx_backfield_article_project_entry_id", "idx_substrate_article_project_entry_id"),
    ("ix_backfield_image_article_id", "ix_substrate_image_article_id"),
    ("ix_backfield_image_image_id", "ix_substrate_image_image_id"),
    ("ix_backfield_location_project_id", "ix_substrate_location_project_id"),
    ("ix_backfield_location_normalized_name", "ix_substrate_location_normalized_name"),
    ("ix_backfield_location_geometry_type", "ix_substrate_location_geometry_type"),
    ("idx_backfield_location_project_status", "idx_substrate_location_project_status"),
    ("idx_backfield_location_project_name", "idx_substrate_location_project_name"),
    ("idx_backfield_location_project_type", "idx_substrate_location_project_type"),
    ("idx_backfield_location_geometry_gist", "idx_substrate_location_geometry_gist"),
    ("ix_backfield_location_mention_article_id", "ix_substrate_location_mention_article_id"),
    ("ix_backfield_location_mention_location_id", "ix_substrate_location_mention_location_id"),
    ("ix_backfield_location_mention_nature", "ix_substrate_location_mention_nature"),
    ("ix_backfield_location_mention_needs_review", "ix_substrate_location_mention_needs_review"),
    ("ix_backfield_location_mention_added", "ix_substrate_location_mention_added"),
    ("ix_backfield_location_mention_edited", "ix_substrate_location_mention_edited"),
    ("ix_backfield_location_mention_deleted", "ix_substrate_location_mention_deleted"),
    ("idx_backfield_location_mention_article_review", "idx_substrate_location_mention_article_review"),
    ("idx_backfield_location_mention_location", "idx_substrate_location_mention_location"),
    (
        "ix_backfield_location_mention_occurrence_location_mention_id",
        "ix_substrate_location_mention_occurrence_location_mention_id",
    ),
    ("ix_backfield_location_mention_occurrence_suppressed", "ix_substrate_location_mention_occurrence_suppressed"),
    ("idx_backfield_location_occurrence_mention_source", "idx_substrate_location_occurrence_mention_source"),
    ("ix_backfield_location_cache_project_id", "ix_substrate_location_cache_project_id"),
    ("ix_backfield_location_cache_normalized_query", "ix_substrate_location_cache_normalized_query"),
    ("ix_backfield_location_cache_geometry_type", "ix_substrate_location_cache_geometry_type"),
    ("idx_backfield_location_cache_project_query_text", "idx_substrate_location_cache_project_query_text"),
    ("idx_backfield_location_cache_project_type", "idx_substrate_location_cache_project_type"),
    ("idx_backfield_location_cache_geometry_gist", "idx_substrate_location_cache_geometry_gist"),
)


def _rename_constraints(conn: Connection, pairs: tuple[tuple[str, str, str], ...]) -> None:
    for table, old_name, new_name in pairs:
        conn.execute(
            sa.text(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"'),
        )


def _rename_indexes(conn: Connection, pairs: tuple[tuple[str, str], ...]) -> None:
    for old_name, new_name in pairs:
        conn.execute(sa.text(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"'))


def upgrade() -> None:
    bind = op.get_bind()
    for old_table, new_table in _TABLE_RENAMES_UP:
        op.rename_table(old_table, new_table)
    _rename_constraints(bind, _CONSTRAINT_RENAMES_UP)
    _rename_indexes(bind, _INDEX_RENAMES_UP)


def downgrade() -> None:
    bind = op.get_bind()
    _rename_indexes(bind, tuple((new, old) for old, new in _INDEX_RENAMES_UP))
    _rename_constraints(bind, tuple((t, new, old) for t, old, new in _CONSTRAINT_RENAMES_UP))
    for old_table, new_table in reversed(_TABLE_RENAMES_UP):
        op.rename_table(new_table, old_table)
