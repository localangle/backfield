"""Add shared content and location substrate tables.

Revision ID: 005_location_schema_foundation
Revises: 004_ws_membership
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "005_location_schema_foundation"
down_revision: Union[str, None] = "004_ws_membership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "backfield_article",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("external_source", sa.Text(), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("pub_date", sa.Date(), nullable=True),
        sa.Column("updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entry_id", sa.Text(), nullable=True),
        sa.Column("s3_bucket", sa.Text(), nullable=True),
        sa.Column("s3_key", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_run_id", sa.Integer(), nullable=True),
        sa.Column("source_item_id", sa.Integer(), nullable=True),
        sa.Column("added", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("edited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
        sa.ForeignKeyConstraint(["project_id"], ["backfield_project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "external_source",
            "external_id",
            name="uq_backfield_article_project_external",
        ),
        sa.UniqueConstraint("project_id", "url", name="uq_backfield_article_project_url"),
    )
    op.create_index("ix_backfield_article_project_id", "backfield_article", ["project_id"], unique=False)
    op.create_index("ix_backfield_article_url", "backfield_article", ["url"], unique=False)
    op.create_index("ix_backfield_article_headline", "backfield_article", ["headline"], unique=False)
    op.create_index("ix_backfield_article_pub_date", "backfield_article", ["pub_date"], unique=False)
    op.create_index("ix_backfield_article_added", "backfield_article", ["added"], unique=False)
    op.create_index("ix_backfield_article_edited", "backfield_article", ["edited"], unique=False)
    op.create_index("ix_backfield_article_deleted", "backfield_article", ["deleted"], unique=False)
    op.create_index(
        "idx_backfield_article_project_pub_date",
        "backfield_article",
        ["project_id", "pub_date"],
        unique=False,
    )
    op.create_index(
        "idx_backfield_article_project_entry_id",
        "backfield_article",
        ["project_id", "entry_id"],
        unique=False,
    )

    op.create_table(
        "backfield_image",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("image_id", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["article_id"], ["backfield_article.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id", "image_id", name="uq_backfield_image_article_image_id"),
    )
    op.create_index("ix_backfield_image_article_id", "backfield_image", ["article_id"], unique=False)
    op.create_index("ix_backfield_image_image_id", "backfield_image", ["image_id"], unique=False)

    op.create_table(
        "backfield_location",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("location_type", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'provisional'"),
        ),
        sa.Column("external_source", sa.Text(), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("identity_fingerprint", sa.Text(), nullable=True),
        sa.Column("geocode_type", sa.Text(), nullable=True),
        sa.Column("formatted_address", sa.Text(), nullable=True),
        sa.Column(
            "parent_ids_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "source_kind",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column(
            "source_details_json",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "geometry",
            Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column("geometry_type", sa.Text(), nullable=True),
        sa.Column(
            "geometry_json",
            sa.JSON(),
            nullable=True,
        ),
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
        sa.ForeignKeyConstraint(["project_id"], ["backfield_project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "external_source",
            "external_id",
            name="uq_backfield_location_project_external",
        ),
        sa.UniqueConstraint(
            "project_id",
            "identity_fingerprint",
            name="uq_backfield_location_project_fingerprint",
        ),
    )
    op.create_index("ix_backfield_location_project_id", "backfield_location", ["project_id"], unique=False)
    op.create_index(
        "ix_backfield_location_normalized_name",
        "backfield_location",
        ["normalized_name"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_location_geometry_type",
        "backfield_location",
        ["geometry_type"],
        unique=False,
    )
    op.create_index(
        "idx_backfield_location_project_status",
        "backfield_location",
        ["project_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_backfield_location_project_name",
        "backfield_location",
        ["project_id", "normalized_name"],
        unique=False,
    )
    op.create_index(
        "idx_backfield_location_project_type",
        "backfield_location",
        ["project_id", "location_type"],
        unique=False,
    )
    op.create_index(
        "idx_backfield_location_geometry_gist",
        "backfield_location",
        ["geometry"],
        unique=False,
        postgresql_using="gist",
    )

    op.create_table(
        "backfield_location_mention",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("role_in_story", sa.Text(), nullable=True),
        sa.Column("nature", sa.Text(), nullable=True),
        sa.Column(
            "nature_secondary_tags_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "review_data_json",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column("added", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("edited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "source_kind",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column(
            "source_details_json",
            sa.JSON(),
            nullable=True,
        ),
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
        sa.ForeignKeyConstraint(["article_id"], ["backfield_article.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["backfield_location.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "article_id",
            "location_id",
            name="uq_backfield_location_mention_article_location",
        ),
    )
    op.create_index(
        "ix_backfield_location_mention_article_id",
        "backfield_location_mention",
        ["article_id"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_location_mention_location_id",
        "backfield_location_mention",
        ["location_id"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_location_mention_nature",
        "backfield_location_mention",
        ["nature"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_location_mention_needs_review",
        "backfield_location_mention",
        ["needs_review"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_location_mention_added",
        "backfield_location_mention",
        ["added"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_location_mention_edited",
        "backfield_location_mention",
        ["edited"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_location_mention_deleted",
        "backfield_location_mention",
        ["deleted"],
        unique=False,
    )
    op.create_index(
        "idx_backfield_location_mention_article_review",
        "backfield_location_mention",
        ["article_id", "needs_review", "deleted"],
        unique=False,
    )
    op.create_index(
        "idx_backfield_location_mention_location",
        "backfield_location_mention",
        ["location_id", "deleted"],
        unique=False,
    )

    op.create_table(
        "backfield_location_mention_occurrence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("location_mention_id", sa.Integer(), nullable=False),
        sa.Column(
            "source_kind",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'system_extraction'"),
        ),
        sa.Column(
            "source_details_json",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column("mention_text", sa.Text(), nullable=False),
        sa.Column("context_text", sa.Text(), nullable=True),
        sa.Column("quote_text", sa.Text(), nullable=True),
        sa.Column("start_char", sa.Integer(), nullable=True),
        sa.Column("end_char", sa.Integer(), nullable=True),
        sa.Column("occurrence_order", sa.Integer(), nullable=True),
        sa.Column(
            "labels_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("suppressed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
        sa.ForeignKeyConstraint(
            ["location_mention_id"],
            ["backfield_location_mention.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_backfield_location_mention_occurrence_location_mention_id",
        "backfield_location_mention_occurrence",
        ["location_mention_id"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_location_mention_occurrence_suppressed",
        "backfield_location_mention_occurrence",
        ["suppressed"],
        unique=False,
    )
    op.create_index(
        "idx_backfield_location_occurrence_mention_source",
        "backfield_location_mention_occurrence",
        ["location_mention_id", "source_kind", "suppressed"],
        unique=False,
    )

    op.create_table(
        "backfield_location_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("normalized_query", sa.Text(), nullable=False),
        sa.Column("query_fingerprint", sa.Text(), nullable=False),
        sa.Column(
            "request_components_json",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column("external_source", sa.Text(), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("location_name", sa.Text(), nullable=False),
        sa.Column("location_type", sa.Text(), nullable=True),
        sa.Column("geocode_type", sa.Text(), nullable=True),
        sa.Column("formatted_address", sa.Text(), nullable=True),
        sa.Column(
            "geometry",
            Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column("geometry_type", sa.Text(), nullable=True),
        sa.Column(
            "geometry_json",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "response_payload_json",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["project_id"], ["backfield_project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "query_fingerprint",
            name="uq_backfield_location_cache_project_query",
        ),
    )
    op.create_index(
        "ix_backfield_location_cache_project_id",
        "backfield_location_cache",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_location_cache_normalized_query",
        "backfield_location_cache",
        ["normalized_query"],
        unique=False,
    )
    op.create_index(
        "ix_backfield_location_cache_geometry_type",
        "backfield_location_cache",
        ["geometry_type"],
        unique=False,
    )
    op.create_index(
        "idx_backfield_location_cache_project_query_text",
        "backfield_location_cache",
        ["project_id", "normalized_query"],
        unique=False,
    )
    op.create_index(
        "idx_backfield_location_cache_project_type",
        "backfield_location_cache",
        ["project_id", "location_type"],
        unique=False,
    )
    op.create_index(
        "idx_backfield_location_cache_geometry_gist",
        "backfield_location_cache",
        ["geometry"],
        unique=False,
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_backfield_location_cache_geometry_gist",
        table_name="backfield_location_cache",
        postgresql_using="gist",
    )
    op.drop_index(
        "idx_backfield_location_cache_project_type",
        table_name="backfield_location_cache",
    )
    op.drop_index(
        "idx_backfield_location_cache_project_query_text",
        table_name="backfield_location_cache",
    )
    op.drop_index(
        "ix_backfield_location_cache_geometry_type",
        table_name="backfield_location_cache",
    )
    op.drop_index(
        "ix_backfield_location_cache_normalized_query",
        table_name="backfield_location_cache",
    )
    op.drop_index("ix_backfield_location_cache_project_id", table_name="backfield_location_cache")
    op.drop_table("backfield_location_cache")

    op.drop_index(
        "idx_backfield_location_occurrence_mention_source",
        table_name="backfield_location_mention_occurrence",
    )
    op.drop_index(
        "ix_backfield_location_mention_occurrence_suppressed",
        table_name="backfield_location_mention_occurrence",
    )
    op.drop_index(
        "ix_backfield_location_mention_occurrence_location_mention_id",
        table_name="backfield_location_mention_occurrence",
    )
    op.drop_table("backfield_location_mention_occurrence")

    op.drop_index(
        "idx_backfield_location_mention_location",
        table_name="backfield_location_mention",
    )
    op.drop_index(
        "idx_backfield_location_mention_article_review",
        table_name="backfield_location_mention",
    )
    op.drop_index("ix_backfield_location_mention_deleted", table_name="backfield_location_mention")
    op.drop_index("ix_backfield_location_mention_edited", table_name="backfield_location_mention")
    op.drop_index("ix_backfield_location_mention_added", table_name="backfield_location_mention")
    op.drop_index(
        "ix_backfield_location_mention_needs_review",
        table_name="backfield_location_mention",
    )
    op.drop_index("ix_backfield_location_mention_nature", table_name="backfield_location_mention")
    op.drop_index(
        "ix_backfield_location_mention_location_id",
        table_name="backfield_location_mention",
    )
    op.drop_index(
        "ix_backfield_location_mention_article_id",
        table_name="backfield_location_mention",
    )
    op.drop_table("backfield_location_mention")

    op.drop_index(
        "idx_backfield_location_geometry_gist",
        table_name="backfield_location",
        postgresql_using="gist",
    )
    op.drop_index("idx_backfield_location_project_type", table_name="backfield_location")
    op.drop_index("idx_backfield_location_project_name", table_name="backfield_location")
    op.drop_index("idx_backfield_location_project_status", table_name="backfield_location")
    op.drop_index("ix_backfield_location_geometry_type", table_name="backfield_location")
    op.drop_index("ix_backfield_location_normalized_name", table_name="backfield_location")
    op.drop_index("ix_backfield_location_project_id", table_name="backfield_location")
    op.drop_table("backfield_location")

    op.drop_index("ix_backfield_image_image_id", table_name="backfield_image")
    op.drop_index("ix_backfield_image_article_id", table_name="backfield_image")
    op.drop_table("backfield_image")

    op.drop_index("idx_backfield_article_project_entry_id", table_name="backfield_article")
    op.drop_index("idx_backfield_article_project_pub_date", table_name="backfield_article")
    op.drop_index("ix_backfield_article_deleted", table_name="backfield_article")
    op.drop_index("ix_backfield_article_edited", table_name="backfield_article")
    op.drop_index("ix_backfield_article_added", table_name="backfield_article")
    op.drop_index("ix_backfield_article_pub_date", table_name="backfield_article")
    op.drop_index("ix_backfield_article_headline", table_name="backfield_article")
    op.drop_index("ix_backfield_article_url", table_name="backfield_article")
    op.drop_index("ix_backfield_article_project_id", table_name="backfield_article")
    op.drop_table("backfield_article")
