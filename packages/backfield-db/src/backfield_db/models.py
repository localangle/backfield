"""ORM models — table prefixes per owning app (see docs/DATABASE.md)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Text, UniqueConstraint, func
from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid4())


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
