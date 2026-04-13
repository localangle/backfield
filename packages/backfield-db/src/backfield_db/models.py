"""ORM models — Agate app tables use `agate_` prefix (see docs/DATABASE.md)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Text, UniqueConstraint, func
from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid4())


class AgateProject(SQLModel, table=True):
    __tablename__ = "agate_project"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(Text, nullable=False))
    slug: str = Field(sa_column=Column(Text, unique=True, nullable=False, index=True))
    settings_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class AgateGraph(SQLModel, table=True):
    __tablename__ = "agate_graph"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(sa_column=Column(Text, nullable=False))
    spec_json: str = Field(sa_column=Column(Text, nullable=False))
    project_id: int = Field(foreign_key="agate_project.id")
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


class AgateProjectSecret(SQLModel, table=True):
    __tablename__ = "agate_project_secret"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_agate_secret_project_key"),)

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="agate_project.id", index=True)
    key: str = Field(sa_column=Column(Text, nullable=False))
    value_encrypted: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
