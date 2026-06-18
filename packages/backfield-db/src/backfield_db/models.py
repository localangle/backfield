"""ORM models — table prefixes per owning app (see docs/DATABASE.md)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from geoalchemy2 import Geometry
from pydantic import ConfigDict
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
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
        UniqueConstraint("organization_id", "name", name="uq_stylebook_organization_name"),
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


class StylebookMembership(SQLModel, table=True):
    """User role assignment for a specific Stylebook.

    Today we only use `role="editor"`; future roles (viewer, etc.) can be added without
    changing the table shape.
    """

    __tablename__ = "stylebook_membership"
    __table_args__ = (
        UniqueConstraint("stylebook_id", "user_id", name="uq_stylebook_member_stylebook_user"),
        Index("ix_stylebook_membership_stylebook_role", "stylebook_id", "role"),
    )

    id: int | None = Field(default=None, primary_key=True)
    stylebook_id: int = Field(foreign_key="stylebook.id", index=True)
    user_id: int = Field(foreign_key="backfield_user.id", index=True)
    role: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class StylebookSlugRedirect(SQLModel, table=True):
    """Prior slug for a stylebook row (used to redirect URLs after rename)."""

    __tablename__ = "stylebook_slug_redirect"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "old_slug",
            name="uq_stylebook_slug_redirect_org_old_slug",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="backfield_organization.id", index=True)
    stylebook_id: int = Field(foreign_key="stylebook.id", index=True)
    old_slug: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class StylebookBundleJob(SQLModel, table=True):
    """Async full stylebook ZIP export/import job (staging on S3-compatible object storage)."""

    __tablename__ = "stylebook_bundle_job"
    __table_args__ = (Index("ix_stylebook_bundle_job_org_status", "organization_id", "status"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    organization_id: int = Field(foreign_key="backfield_organization.id", index=True)
    kind: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(
        default="queued",
        sa_column=Column(Text, nullable=False, server_default="queued"),
    )
    created_by_user_id: int | None = Field(
        default=None,
        foreign_key="backfield_user.id",
        index=True,
    )
    source_stylebook_id: int | None = Field(
        default=None,
        foreign_key="stylebook.id",
        index=True,
    )
    result_stylebook_id: int | None = Field(
        default=None,
        foreign_key="stylebook.id",
        index=True,
    )
    s3_bucket: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    s3_key: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    progress_json: dict[str, Any] | list[Any] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    import_request_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class StylebookCleanupDismissal(SQLModel, table=True):
    """Editor dismissal of a cleanup issue (duplicate pair or list item)."""

    __tablename__ = "stylebook_cleanup_dismissal"
    __table_args__ = (
        UniqueConstraint(
            "stylebook_id",
            "check_id",
            "pair_key",
            name="uq_stylebook_cleanup_dismissal_key",
        ),
        Index("ix_stylebook_cleanup_dismissal_stylebook_check", "stylebook_id", "check_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    stylebook_id: int = Field(foreign_key="stylebook.id", index=True)
    check_id: str = Field(sa_column=Column(Text, nullable=False))
    pair_key: str = Field(
        sa_column=Column(Text, nullable=False),
        description="Sorted canonical pair 'a|b' or single canonical id for list checks.",
    )
    created_by_user_id: int | None = Field(
        default=None,
        foreign_key="backfield_user.id",
        index=True,
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class StylebookLocationCanonical(SQLModel, table=True):
    """Canonical location row within a Stylebook."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    __tablename__ = "stylebook_location_canonical"
    __table_args__ = (
        UniqueConstraint(
            "stylebook_id",
            "slug",
            name="uq_stylebook_location_canonical_stylebook_slug",
        ),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    stylebook_id: int = Field(foreign_key="stylebook.id", index=True)
    label: str = Field(sa_column=Column(Text, nullable=False))
    slug: str = Field(sa_column=Column(Text, nullable=False))
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
    h3_cell: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    h3_resolution: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    country_code: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    subdivision_code: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    city_name: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    district_kind: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    district_number: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    district_key: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
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
    location_canonical_id: str = Field(foreign_key="stylebook_location_canonical.id", index=True)
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


class StylebookLocationMeta(SQLModel, table=True):
    """Arbitrary JSON metadata rows for a canonical location (tags, research blobs, etc.)."""

    __tablename__ = "stylebook_location_meta"
    __table_args__ = (
        Index(
            "ix_stylebook_location_meta_canonical_type",
            "stylebook_location_canonical_id",
            "meta_type",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    stylebook_location_canonical_id: str = Field(
        foreign_key="stylebook_location_canonical.id",
        index=True,
    )
    meta_type: str = Field(sa_column=Column(Text, nullable=False, index=True))
    data_json: Any | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    added: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    edited: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    deleted: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class StylebookPersonCanonical(SQLModel, table=True):
    """Canonical person row within a Stylebook."""

    __tablename__ = "stylebook_person_canonical"
    __table_args__ = (
        UniqueConstraint(
            "stylebook_id",
            "slug",
            name="uq_stylebook_person_canonical_stylebook_slug",
        ),
        Index("ix_stylebook_person_canonical_stylebook_type", "stylebook_id", "person_type"),
        Index(
            "ix_stylebook_person_canonical_stylebook_public_figure",
            "stylebook_id",
            "public_figure",
        ),
        Index(
            "ix_stylebook_person_canonical_stylebook_sort_key",
            "stylebook_id",
            "sort_key",
        ),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    stylebook_id: int = Field(foreign_key="stylebook.id", index=True)
    label: str = Field(sa_column=Column(Text, nullable=False))
    slug: str = Field(sa_column=Column(Text, nullable=False))
    title: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    affiliation: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    public_figure: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    person_type: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    sort_key: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    primary_substrate_person_id: int | None = Field(
        default=None,
        foreign_key="substrate_person.id",
        index=True,
    )
    status: str = Field(
        default="active",
        sa_column=Column(Text, nullable=False, server_default="active"),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class StylebookPersonAlias(SQLModel, table=True):
    """Alias string for a canonical person (hybrid provenance)."""

    __tablename__ = "stylebook_person_alias"
    __table_args__ = (
        UniqueConstraint(
            "person_canonical_id",
            "normalized_alias",
            name="uq_stylebook_person_alias_canonical_normalized",
        ),
        Index("ix_stylebook_person_alias_normalized", "normalized_alias"),
    )

    id: int | None = Field(default=None, primary_key=True)
    person_canonical_id: str = Field(foreign_key="stylebook_person_canonical.id", index=True)
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


class StylebookPersonMeta(SQLModel, table=True):
    """Arbitrary JSON metadata rows for a canonical person (tags, research blobs, etc.)."""

    __tablename__ = "stylebook_person_meta"
    __table_args__ = (
        Index(
            "ix_stylebook_person_meta_canonical_type",
            "stylebook_person_canonical_id",
            "meta_type",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    stylebook_person_canonical_id: str = Field(
        foreign_key="stylebook_person_canonical.id",
        index=True,
    )
    meta_type: str = Field(sa_column=Column(Text, nullable=False, index=True))
    data_json: Any | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    added: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    edited: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    deleted: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class StylebookOrganizationCanonical(SQLModel, table=True):
    """Canonical organization row within a Stylebook."""

    __tablename__ = "stylebook_organization_canonical"
    __table_args__ = (
        UniqueConstraint(
            "stylebook_id",
            "slug",
            name="uq_stylebook_organization_canonical_stylebook_slug",
        ),
        Index(
            "ix_stylebook_organization_canonical_stylebook_type",
            "stylebook_id",
            "organization_type",
        ),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    stylebook_id: int = Field(foreign_key="stylebook.id", index=True)
    label: str = Field(sa_column=Column(Text, nullable=False))
    slug: str = Field(sa_column=Column(Text, nullable=False))
    organization_type: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    primary_substrate_organization_id: int | None = Field(
        default=None,
        foreign_key="substrate_organization.id",
        index=True,
    )
    status: str = Field(
        default="active",
        sa_column=Column(Text, nullable=False, server_default="active"),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class StylebookOrganizationAlias(SQLModel, table=True):
    """Alias string for a canonical organization (hybrid provenance)."""

    __tablename__ = "stylebook_organization_alias"
    __table_args__ = (
        UniqueConstraint(
            "organization_canonical_id",
            "normalized_alias",
            name="uq_stylebook_organization_alias_canonical_normalized",
        ),
        Index("ix_stylebook_organization_alias_normalized", "normalized_alias"),
    )

    id: int | None = Field(default=None, primary_key=True)
    organization_canonical_id: str = Field(
        foreign_key="stylebook_organization_canonical.id",
        index=True,
    )
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


class StylebookOrganizationMeta(SQLModel, table=True):
    """Arbitrary JSON metadata rows for a canonical organization."""

    __tablename__ = "stylebook_organization_meta"
    __table_args__ = (
        Index(
            "ix_stylebook_organization_meta_canonical_type",
            "stylebook_organization_canonical_id",
            "meta_type",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    stylebook_organization_canonical_id: str = Field(
        foreign_key="stylebook_organization_canonical.id",
        index=True,
    )
    meta_type: str = Field(sa_column=Column(Text, nullable=False, index=True))
    data_json: Any | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    added: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    edited: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    deleted: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class StylebookConnection(SQLModel, table=True):
    """Directed edge between two canonical entities within a project (polymorphic entity ids).

    ``from_entity_id`` / ``to_entity_id`` are TEXT UUID strings for ``location``, ``person``,
    and ``organization`` entities; decimal strings for stub work ids until that catalog uses UUIDs.

    ``evidence_json`` is optional creation evidence for auto-linked edges (see
    ``backfield_entities.connections.evidence``). Manual connections leave it null.
    """

    __tablename__ = "stylebook_connections"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "from_entity_type",
            "from_entity_id",
            "to_entity_type",
            "to_entity_id",
            "nature",
            name="uq_stylebook_connection_exact_edge",
        ),
        Index(
            "ix_stylebook_connection_from",
            "project_id",
            "from_entity_type",
            "from_entity_id",
        ),
        Index(
            "ix_stylebook_connection_to",
            "project_id",
            "to_entity_type",
            "to_entity_id",
        ),
        Index("ix_stylebook_connection_nature", "project_id", "nature"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    from_entity_type: str = Field(sa_column=Column(Text, nullable=False, index=True))
    from_entity_id: str = Field(sa_column=Column(Text, nullable=False, index=True))
    to_entity_type: str = Field(sa_column=Column(Text, nullable=False, index=True))
    to_entity_id: str = Field(sa_column=Column(Text, nullable=False, index=True))
    nature: str = Field(sa_column=Column(Text, nullable=False, index=True))
    evidence_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    created_at: datetime = Field(
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


class BackfieldOrganizationIntegrationSecret(SQLModel, table=True):
    """Organization-scoped encrypted integration secret (AI provider keys first)."""

    __tablename__ = "backfield_organization_integration_secret"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "integration_key",
            name="uq_backfield_org_integration_secret_org_key",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="backfield_organization.id", index=True)
    integration_key: str = Field(sa_column=Column(Text, nullable=False))
    credential_display_name: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    api_base: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    value_encrypted: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


# ----- Shared AI model configuration and usage tracking (backfield_ai_*) -----


class BackfieldAiModelConfig(SQLModel, table=True):
    """Organization-owned AI model configuration shared by Agate and Stylebook."""

    __tablename__ = "backfield_ai_model_config"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_backfield_ai_model_config_org_name",
        ),
        Index(
            "ix_backfield_ai_model_config_org_provider_model",
            "organization_id",
            "provider",
            "provider_model_id",
        ),
        Index(
            "ix_backfield_ai_model_config_org_status_kind",
            "organization_id",
            "status",
            "model_kind",
        ),
        Index(
            "ix_bf_ai_model_integration_secret",
            "integration_secret_id",
        ),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    organization_id: int = Field(foreign_key="backfield_organization.id", index=True)
    name: str = Field(sa_column=Column(Text, nullable=False))
    provider: str = Field(sa_column=Column(Text, nullable=False))
    provider_model_id: str = Field(sa_column=Column(Text, nullable=False))
    model_kind: str = Field(
        default="generative",
        sa_column=Column(Text, nullable=False, server_default="generative"),
    )
    status: str = Field(
        default="active",
        sa_column=Column(Text, nullable=False, server_default="active"),
    )
    capabilities_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    litellm_model: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    integration_secret_id: int | None = Field(
        default=None,
        foreign_key="backfield_organization_integration_secret.id",
        nullable=True,
    )
    config_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    input_token_price: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(18, 12), nullable=True),
    )
    output_token_price: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(18, 12), nullable=True),
    )
    currency: str = Field(
        default="USD",
        sa_column=Column(Text, nullable=False, server_default="USD"),
    )
    latest_test_status: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    latest_tested_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    latest_test_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class BackfieldAiProjectModelOverride(SQLModel, table=True):
    """Project-level availability override for inherited organization AI models."""

    __tablename__ = "backfield_ai_project_model_override"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "model_config_id",
            name="uq_backfield_ai_project_model_override_project_model",
        ),
        Index(
            "ix_backfield_ai_project_model_override_project_enabled",
            "project_id",
            "enabled",
        ),
        Index(
            "ix_backfield_ai_override_integration_secret_id",
            "integration_secret_id",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    model_config_id: str = Field(foreign_key="backfield_ai_model_config.id", index=True)
    integration_secret_id: int | None = Field(
        default=None,
        foreign_key="backfield_organization_integration_secret.id",
        nullable=True,
    )
    enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class BackfieldAiDefaultModelRole(SQLModel, table=True):
    """Default model assignment for an organization or one of its projects."""

    __tablename__ = "backfield_ai_default_model_role"
    __table_args__ = (
        CheckConstraint(
            "(organization_id IS NOT NULL AND project_id IS NULL) "
            "OR (organization_id IS NULL AND project_id IS NOT NULL)",
            name="ck_backfield_ai_default_model_role_one_scope",
        ),
        Index(
            "uq_backfield_ai_default_model_role_org_role",
            "organization_id",
            "role",
            unique=True,
            postgresql_where=text("organization_id IS NOT NULL AND project_id IS NULL"),
            sqlite_where=text("organization_id IS NOT NULL AND project_id IS NULL"),
        ),
        Index(
            "uq_backfield_ai_default_model_role_project_role",
            "project_id",
            "role",
            unique=True,
            postgresql_where=text("project_id IS NOT NULL AND organization_id IS NULL"),
            sqlite_where=text("project_id IS NOT NULL AND organization_id IS NULL"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int | None = Field(
        default=None,
        foreign_key="backfield_organization.id",
        index=True,
    )
    project_id: int | None = Field(default=None, foreign_key="backfield_project.id", index=True)
    role: str = Field(sa_column=Column(Text, nullable=False))
    model_config_id: str = Field(foreign_key="backfield_ai_model_config.id", index=True)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class BackfieldAiCallRecord(SQLModel, table=True):
    """One persisted attempt to call an AI model during execution."""

    __tablename__ = "backfield_ai_call_record"
    __table_args__ = (
        Index("ix_backfield_ai_call_record_project_created", "project_id", "created_at"),
        Index("ix_backfield_ai_call_record_run_node", "run_id", "node_id"),
        Index("ix_backfield_ai_call_record_run_status", "run_id", "status"),
        Index("ix_backfield_ai_call_record_model_status", "model_config_id", "status"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    run_id: str | None = Field(default=None, foreign_key="agate_run.id", index=True)
    processed_item_id: int | None = Field(
        default=None,
        foreign_key="agate_processed_item.id",
        index=True,
    )
    node_id: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    node_type: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    model_config_id: str | None = Field(
        default=None,
        foreign_key="backfield_ai_model_config.id",
        index=True,
    )
    model_config_snapshot_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    provider: str = Field(sa_column=Column(Text, nullable=False))
    provider_model_id: str = Field(sa_column=Column(Text, nullable=False))
    model_kind: str = Field(
        default="generative",
        sa_column=Column(Text, nullable=False, server_default="generative"),
    )
    status: str = Field(sa_column=Column(Text, nullable=False, index=True))
    attempt_number: int = Field(default=1, nullable=False)
    prompt_tokens: int | None = Field(default=None)
    completion_tokens: int | None = Field(default=None)
    total_tokens: int | None = Field(default=None)
    estimated_cost: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(18, 12), nullable=True),
    )
    currency: str = Field(
        default="USD",
        sa_column=Column(Text, nullable=False, server_default="USD"),
    )
    cost_estimate_source: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    cost_estimate_incomplete: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    latency_ms: int | None = Field(default=None)
    provider_request_id: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    error_type: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
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
        Index("idx_substrate_location_project_h3_resolution", "project_id", "h3_resolution"),
        Index("idx_substrate_location_project_h3_cell", "project_id", "h3_cell"),
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
    stylebook_location_canonical_id: str | None = Field(
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
    h3_cell: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    h3_resolution: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    # GeocodeAgent structured router audit (from ``agate_geocode_router_audit``).
    geocode_router_audit_json: dict[str, Any] | list[Any] | None = Field(
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


class SubstratePerson(SQLModel, table=True):
    """Durable shared person entity for stateful article ingestion."""

    __tablename__ = "substrate_person"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "external_source",
            "external_id",
            name="uq_substrate_person_project_external",
        ),
        UniqueConstraint(
            "project_id",
            "identity_fingerprint",
            name="uq_substrate_person_project_fingerprint",
        ),
        Index("idx_substrate_person_project_status", "project_id", "status"),
        Index("idx_substrate_person_project_name", "project_id", "normalized_name"),
        Index("idx_substrate_person_project_type", "project_id", "person_type"),
        Index(
            "idx_substrate_person_project_public_figure",
            "project_id",
            "public_figure",
        ),
        Index(
            "idx_substrate_person_project_sort_key",
            "project_id",
            "sort_key",
        ),
        Index(
            "ix_substrate_person_project_canonical",
            "project_id",
            "stylebook_person_canonical_id",
        ),
        Index(
            "ix_substrate_person_project_link_status",
            "project_id",
            "canonical_link_status",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    name: str = Field(sa_column=Column(Text, nullable=False))
    normalized_name: str = Field(sa_column=Column(Text, nullable=False, index=True))
    title: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    affiliation: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    public_figure: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    person_type: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    sort_key: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(
        default="provisional",
        sa_column=Column(Text, nullable=False, server_default="provisional"),
    )
    stylebook_person_canonical_id: str | None = Field(
        default=None,
        foreign_key="stylebook_person_canonical.id",
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


class SubstratePersonMention(SQLModel, table=True):
    """One aggregate article-to-person association."""

    __tablename__ = "substrate_person_mention"
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "person_id",
            name="uq_substrate_person_mention_article_person",
        ),
        Index(
            "idx_substrate_person_mention_article_review",
            "article_id",
            "needs_review",
            "deleted",
        ),
        Index("idx_substrate_person_mention_person", "person_id", "deleted"),
    )

    id: int | None = Field(default=None, primary_key=True)
    article_id: int = Field(foreign_key="substrate_article.id", index=True)
    person_id: int = Field(foreign_key="substrate_person.id", index=True)
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


class SubstratePersonMentionOccurrence(SQLModel, table=True):
    """Supporting textual evidence for a person mention aggregate."""

    __tablename__ = "substrate_person_mention_occurrence"
    __table_args__ = (
        Index(
            "idx_substrate_person_occurrence_mention_source",
            "person_mention_id",
            "source_kind",
            "suppressed",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    person_mention_id: int = Field(foreign_key="substrate_person_mention.id", index=True)
    source_kind: str = Field(
        default="system_extraction",
        sa_column=Column(Text, nullable=False, server_default="system_extraction"),
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


class SubstrateOrganization(SQLModel, table=True):
    """Durable shared organization entity for stateful article ingestion."""

    __tablename__ = "substrate_organization"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "external_source",
            "external_id",
            name="uq_substrate_organization_project_external",
        ),
        UniqueConstraint(
            "project_id",
            "identity_fingerprint",
            name="uq_substrate_organization_project_fingerprint",
        ),
        Index("idx_substrate_organization_project_status", "project_id", "status"),
        Index("idx_substrate_organization_project_name", "project_id", "normalized_name"),
        Index("idx_substrate_organization_project_type", "project_id", "organization_type"),
        Index(
            "ix_substrate_organization_project_canonical",
            "project_id",
            "stylebook_organization_canonical_id",
        ),
        Index(
            "ix_substrate_organization_project_link_status",
            "project_id",
            "canonical_link_status",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="backfield_project.id", index=True)
    name: str = Field(sa_column=Column(Text, nullable=False))
    normalized_name: str = Field(sa_column=Column(Text, nullable=False, index=True))
    organization_type: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(
        default="provisional",
        sa_column=Column(Text, nullable=False, server_default="provisional"),
    )
    stylebook_organization_canonical_id: str | None = Field(
        default=None,
        foreign_key="stylebook_organization_canonical.id",
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


class SubstrateOrganizationMention(SQLModel, table=True):
    """One aggregate article-to-organization association."""

    __tablename__ = "substrate_organization_mention"
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "organization_id",
            name="uq_substrate_organization_mention_article_organization",
        ),
        Index(
            "idx_substrate_organization_mention_article_review",
            "article_id",
            "needs_review",
            "deleted",
        ),
        Index("idx_substrate_organization_mention_organization", "organization_id", "deleted"),
    )

    id: int | None = Field(default=None, primary_key=True)
    article_id: int = Field(foreign_key="substrate_article.id", index=True)
    organization_id: int = Field(foreign_key="substrate_organization.id", index=True)
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


class SubstrateOrganizationMentionOccurrence(SQLModel, table=True):
    """Supporting textual evidence for an organization mention aggregate."""

    __tablename__ = "substrate_organization_mention_occurrence"
    __table_args__ = (
        Index(
            "idx_substrate_organization_occurrence_mention_source",
            "organization_mention_id",
            "source_kind",
            "suppressed",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    organization_mention_id: int = Field(
        foreign_key="substrate_organization_mention.id",
        index=True,
    )
    source_kind: str = Field(
        default="system_extraction",
        sa_column=Column(Text, nullable=False, server_default="system_extraction"),
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
        Index("idx_substrate_location_cache_project_h3_resolution", "project_id", "h3_resolution"),
        Index("idx_substrate_location_cache_project_h3_cell", "project_id", "h3_cell"),
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
    h3_cell: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    h3_resolution: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
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
    description: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
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
    #: When true, the next DBOutput persist for this run replaces pipeline geography per article.
    replace_article_geography_on_persist: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class AgateProcessedItem(SQLModel, table=True):
    """Per-S3-object execution unit for S3Input batch runs (parent ``agate_run``)."""

    __tablename__ = "agate_processed_item"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="agate_run.id", index=True)
    source_file: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    input_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(
        default="pending",
        sa_column=Column(Text, nullable=False),
    )
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    result_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    #: Human review overlay (JSON text); immutable model output stays in ``result_json``.
    overlay_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    overlay_version: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    #: Materialized model + overlay for JSON export; immutable output stays in ``result_json``.
    reviewed_output_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    #: When true, next DBOutput persist replaces pipeline geography for this item's article.
    replace_article_geography_on_persist: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    #: Denormalized link for public article provenance and hub queries (set on persist).
    substrate_article_id: int | None = Field(
        default=None,
        foreign_key="substrate_article.id",
        index=True,
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class AgateNodeTiming(SQLModel, table=True):
    """Per-node wall-clock timing for a processed item graph execution."""

    __tablename__ = "agate_node_timing"

    id: str = Field(default_factory=_uuid, primary_key=True)
    run_id: str = Field(
        sa_column=Column(
            Text,
            ForeignKey("agate_run.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    processed_item_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("agate_processed_item.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    node_id: str = Field(sa_column=Column(Text, nullable=False))
    node_type: str = Field(sa_column=Column(Text, nullable=False))
    elapsed_s: float = Field(sa_column=Column(Float, nullable=False))
    created_at: datetime = Field(
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
