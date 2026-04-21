"""ORM models — table prefixes per owning app (see docs/DATABASE.md)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import uuid4

from geoalchemy2 import Geometry
from pydantic import ConfigDict
from sqlalchemy import JSON, Boolean, Column, DateTime, Index, Text, UniqueConstraint, func, text
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid4())


class _PostgresGeometry(TypeDecorator):
    """Render true PostGIS geometry on Postgres and plain text elsewhere."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(
                Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False)
            )
        return dialect.type_descriptor(Text())


# ----- Identity & tenancy (backfield_*) -----


class BackfieldOrganization(SQLModel, table=True):
    __tablename__ = "backfield_organization"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(Text, nullable=False))
    slug: str = Field(sa_column=Column(Text, unique=True, nullable=False, index=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class BackfieldWorkspace(SQLModel, table=True):
    """Optional grouping under an organization (domain-neutral)."""

    __tablename__ = "backfield_workspace"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_backfield_workspace_org_slug"),
    )

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="backfield_organization.id", index=True)
    stylebook_id: int = Field(foreign_key="stylebook.id", index=True)
    name: str = Field(sa_column=Column(Text, nullable=False))
    slug: str = Field(sa_column=Column(Text, nullable=False, index=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class BackfieldUser(SQLModel, table=True):
    __tablename__ = "backfield_user"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(sa_column=Column(Text, unique=True, nullable=False, index=True))
    password_hash: str = Field(sa_column=Column(Text, nullable=False))
    display_name: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    disabled_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class BackfieldOrganizationMembership(SQLModel, table=True):
    __tablename__ = "backfield_organization_membership"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_backfield_org_member_user_org"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="backfield_user.id", index=True)
    organization_id: int = Field(foreign_key="backfield_organization.id", index=True)
    role: str = Field(
        sa_column=Column(Text, nullable=False),
        description="e.g. org_admin, member",
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class BackfieldProject(SQLModel, table=True):
    """Canonical project for Agate, Stylebook vault, and future Core import APIs."""

    __tablename__ = "backfield_project"

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="backfield_organization.id", index=True)
    workspace_id: int | None = Field(
        default=None,
        foreign_key="backfield_workspace.id",
        index=True,
    )
    name: str = Field(sa_column=Column(Text, nullable=False))
    slug: str = Field(sa_column=Column(Text, unique=True, nullable=False, index=True))
    settings_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class BackfieldProjectMembership(SQLModel, table=True):
    __tablename__ = "backfield_project_membership"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", name="uq_backfield_project_member_user_proj"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="backfield_user.id", index=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    role: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class Stylebook(SQLModel, table=True):
    """Org-scoped Stylebook (canonical entities, editorial rules)."""

    __tablename__ = "stylebook"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_stylebook_organization_slug"),
        Index(
            "uq_stylebook_org_one_default",
            "organization_id",
            unique=True,
            postgresql_where=text("is_default = true"),
            sqlite_where=text("is_default = 1"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="backfield_organization.id", index=True)
    slug: str = Field(sa_column=Column(Text, nullable=False))
    name: str = Field(sa_column=Column(Text, nullable=False))
    is_default: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class StylebookLocationCanonical(SQLModel, table=True):
    """Canonical location row within a Stylebook."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    __tablename__ = "stylebook_location_canonical"

    id: int | None = Field(default=None, primary_key=True)
    stylebook_id: int = Field(foreign_key="stylebook.id", index=True)
    label: str = Field(sa_column=Column(Text, nullable=False))
    location_type: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    formatted_address: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    primary_substrate_location_id: int | None = Field(
        default=None,
        foreign_key="substrate_location.id",
        index=True,
    )
    status: str = Field(
        default="active",
        sa_column=Column(Text, nullable=False, server_default="active"),
    )
    geometry: object | None = Field(
        default=None,
        sa_column=Column(_PostgresGeometry(), nullable=True),
    )
    geometry_type: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True, index=True),
    )
    geometry_json: dict | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class StylebookLocationAlias(SQLModel, table=True):
    """Alias string for a canonical location (hybrid provenance)."""

    __tablename__ = "stylebook_location_alias"
    __table_args__ = (
        UniqueConstraint(
            "location_canonical_id",
            "normalized_alias",
            name="uq_stylebook_location_alias_canonical_normalized",
        ),
        Index("ix_stylebook_location_alias_normalized", "normalized_alias"),
    )

    id: int | None = Field(default=None, primary_key=True)
    location_canonical_id: int = Field(foreign_key="stylebook_location_canonical.id", index=True)
    alias_text: str = Field(sa_column=Column(Text, nullable=False))
    normalized_alias: str = Field(sa_column=Column(Text, nullable=False))
    provenance: str = Field(sa_column=Column(Text, nullable=False))
    suppressed: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class BackfieldWorkspaceMembership(SQLModel, table=True):
    """User access to a workspace (implies all projects in that workspace for members)."""

    __tablename__ = "backfield_workspace_membership"
    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id", name="uq_backfield_ws_member_user_ws"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="backfield_user.id", index=True)
    workspace_id: int = Field(foreign_key="backfield_workspace.id", index=True)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class BackfieldApiCredential(SQLModel, table=True):
    __tablename__ = "backfield_api_credential"
    __table_args__ = (UniqueConstraint("key_prefix", name="uq_backfield_api_cred_prefix"),)

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    user_id: int | None = Field(default=None, foreign_key="backfield_user.id", index=True)
    credential_type: str = Field(
        sa_column=Column(Text, nullable=False),
        description="user or service",
    )
    key_prefix: str = Field(sa_column=Column(Text, nullable=False, index=True))
    key_hash: str = Field(sa_column=Column(Text, nullable=False))
    label: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    revoked_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    last_used_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class BackfieldProjectSecret(SQLModel, table=True):
    __tablename__ = "backfield_project_secret"
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_backfield_secret_project_key"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    key: str = Field(sa_column=Column(Text, nullable=False))
    value_encrypted: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


# ----- Shared content + entity substrate (substrate_* — not tenancy `backfield_*`) -----


class SubstrateArticle(SQLModel, table=True):
    """Project-scoped article/content item used by stateful ingestion."""

    __tablename__ = "substrate_article"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "external_source",
            "external_id",
            name="uq_substrate_article_project_external",
        ),
        UniqueConstraint("project_id", "url", name="uq_substrate_article_project_url"),
        Index("idx_substrate_article_project_pub_date", "project_id", "pub_date"),
        Index("idx_substrate_article_project_entry_id", "project_id", "entry_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    external_source: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    external_id: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    url: str | None = Field(default=None, sa_column=Column(Text, nullable=True, index=True))
    headline: str = Field(sa_column=Column(Text, nullable=False, index=True))
    author: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    pub_date: date | None = Field(default=None, index=True)
    updated: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    entry_id: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    s3_bucket: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    s3_key: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    text: str = Field(sa_column=Column(Text, nullable=False))
    source_run_id: str | None = Field(default=None, foreign_key="agate_run.id", index=True)
    source_item_id: int | None = Field(default=None)
    added: bool = Field(default=False, index=True)
    edited: bool = Field(default=False, index=True)
    deleted: bool = Field(default=False, index=True)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class SubstrateImage(SQLModel, table=True):
    """Image attached to a substrate article row."""

    __tablename__ = "substrate_image"
    __table_args__ = (
        UniqueConstraint("article_id", "image_id", name="uq_substrate_image_article_image_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    article_id: int = Field(foreign_key="substrate_article.id", index=True)
    image_id: str = Field(sa_column=Column(Text, nullable=False, index=True))
    url: str = Field(sa_column=Column(Text, nullable=False))
    caption: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class SubstrateLocation(SQLModel, table=True):
    """Durable shared location entity for stateful article ingestion."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    __tablename__ = "substrate_location"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "external_source",
            "external_id",
            name="uq_substrate_location_project_external",
        ),
        UniqueConstraint(
            "project_id",
            "identity_fingerprint",
            name="uq_substrate_location_project_fingerprint",
        ),
        Index("idx_substrate_location_project_status", "project_id", "status"),
        Index("idx_substrate_location_project_name", "project_id", "normalized_name"),
        Index("idx_substrate_location_project_type", "project_id", "location_type"),
        Index(
            "ix_substrate_location_project_canonical",
            "project_id",
            "stylebook_location_canonical_id",
        ),
        Index(
            "ix_substrate_location_project_link_status",
            "project_id",
            "canonical_link_status",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    name: str = Field(sa_column=Column(Text, nullable=False))
    normalized_name: str = Field(sa_column=Column(Text, nullable=False, index=True))
    location_type: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(
        default="provisional",
        sa_column=Column(Text, nullable=False, server_default="provisional"),
    )
    stylebook_location_canonical_id: int | None = Field(
        default=None,
        foreign_key="stylebook_location_canonical.id",
        index=True,
    )
    canonical_link_status: str = Field(
        default="unlinked",
        sa_column=Column(Text, nullable=False, server_default="unlinked"),
    )
    canonical_review_reasons_json: list[Any] | dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    external_source: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    external_id: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    identity_fingerprint: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    geocode_type: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    formatted_address: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    source_kind: str = Field(
        default="unknown",
        sa_column=Column(Text, nullable=False, server_default="unknown"),
    )
    source_details_json: dict | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    geometry: object | None = Field(
        default=None,
        sa_column=Column(_PostgresGeometry(), nullable=True),
    )
    geometry_type: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True, index=True),
    )
    geometry_json: dict | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class SubstrateLocationMention(SQLModel, table=True):
    """One aggregate article-to-location association."""

    __tablename__ = "substrate_location_mention"
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "location_id",
            name="uq_substrate_location_mention_article_location",
        ),
        Index(
            "idx_substrate_location_mention_article_review",
            "article_id",
            "needs_review",
            "deleted",
        ),
        Index("idx_substrate_location_mention_location", "location_id", "deleted"),
    )

    id: int | None = Field(default=None, primary_key=True)
    article_id: int = Field(foreign_key="substrate_article.id", index=True)
    location_id: int = Field(foreign_key="substrate_location.id", index=True)
    role_in_story: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    nature: str | None = Field(default=None, sa_column=Column(Text, nullable=True, index=True))
    nature_secondary_tags_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    needs_review: bool = Field(default=False, index=True)
    review_data_json: dict | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    added: bool = Field(default=False, index=True)
    edited: bool = Field(default=False, index=True)
    deleted: bool = Field(default=False, index=True)
    source_kind: str = Field(
        default="unknown",
        sa_column=Column(Text, nullable=False, server_default="unknown"),
    )
    source_details_json: dict | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class SubstrateLocationMentionOccurrence(SQLModel, table=True):
    """Supporting textual evidence for a location mention aggregate."""

    __tablename__ = "substrate_location_mention_occurrence"
    __table_args__ = (
        Index(
            "idx_substrate_location_occurrence_mention_source",
            "location_mention_id",
            "source_kind",
            "suppressed",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    location_mention_id: int = Field(foreign_key="substrate_location_mention.id", index=True)
    source_kind: str = Field(
        default="system_extraction",
        sa_column=Column(Text, nullable=False, server_default="system_extraction")
    )
    source_details_json: dict | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    mention_text: str = Field(sa_column=Column(Text, nullable=False))
    quote_text: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    start_char: int | None = Field(default=None)
    end_char: int | None = Field(default=None)
    occurrence_order: int | None = Field(default=None)
    labels_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    suppressed: bool = Field(default=False, index=True)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class SubstrateLocationCache(SQLModel, table=True):
    """Project-scoped dumb cache of external geocoding or resolution results."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    __tablename__ = "substrate_location_cache"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "query_fingerprint",
            name="uq_substrate_location_cache_project_query",
        ),
        Index("idx_substrate_location_cache_project_query_text", "project_id", "normalized_query"),
        Index("idx_substrate_location_cache_project_type", "project_id", "location_type"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    query_text: str = Field(sa_column=Column(Text, nullable=False))
    normalized_query: str = Field(sa_column=Column(Text, nullable=False, index=True))
    query_fingerprint: str = Field(sa_column=Column(Text, nullable=False))
    request_components_json: dict | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    external_source: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    external_id: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    location_name: str = Field(sa_column=Column(Text, nullable=False))
    location_type: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    geocode_type: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    formatted_address: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    geometry: object | None = Field(
        default=None,
        sa_column=Column(_PostgresGeometry(), nullable=True),
    )
    geometry_type: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True, index=True),
    )
    geometry_json: dict | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    response_payload_json: dict | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


# ----- Agate graphs / runs (agate_* — unchanged names) -----


class AgateGraph(SQLModel, table=True):
    __tablename__ = "agate_graph"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(sa_column=Column(Text, nullable=False))
    spec_json: str = Field(sa_column=Column(Text, nullable=False))
    project_id: int = Field(foreign_key="backfield_project.id")
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class AgateRun(SQLModel, table=True):
    __tablename__ = "agate_run"

    id: str = Field(default_factory=_uuid, primary_key=True)
    graph_id: str = Field(foreign_key="agate_graph.id", index=True)
    status: str = Field(default="pending", sa_column=Column(Text, nullable=False))
    result_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class AgateTemplate(SQLModel, table=True):
    __tablename__ = "agate_template"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(sa_column=Column(Text, nullable=False))
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    category: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    spec_json: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
