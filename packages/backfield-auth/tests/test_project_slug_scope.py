"""Authenticated project slug resolution stays inside one organization."""

from __future__ import annotations

import pytest
from backfield_auth.gate import resolve_project_by_slug
from backfield_db import BackfieldOrganization, BackfieldProject, BackfieldWorkspace, Stylebook
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine


def _project(session: Session, org_slug: str, project_slug: str) -> BackfieldProject:
    organization = BackfieldOrganization(name=org_slug.title(), slug=org_slug)
    session.add(organization)
    session.commit()
    session.refresh(organization)
    stylebook = Stylebook(
        organization_id=int(organization.id),
        name="Default",
        slug="default",
        is_default=True,
    )
    session.add(stylebook)
    session.commit()
    session.refresh(stylebook)
    workspace = BackfieldWorkspace(
        organization_id=int(organization.id),
        stylebook_id=int(stylebook.id),
        name="Default",
        slug="default",
    )
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    project = BackfieldProject(
        organization_id=int(organization.id),
        stylebook_id=int(stylebook.id),
        workspace_id=int(workspace.id),
        name="News",
        slug=project_slug,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def test_session_project_slug_resolution_uses_active_organization() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        first = _project(session, "first", "news")
        second = _project(session, "second", "news")
        resolved = resolve_project_by_slug(
            session,
            {"type": "session", "organization_id": second.organization_id},
            "news",
        )
        assert resolved.id == second.id
        assert resolved.id != first.id


def test_project_key_validates_its_bound_project_slug() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project = _project(session, "first", "news")
        with pytest.raises(HTTPException) as exc:
            resolve_project_by_slug(
                session,
                {"type": "api_key", "project_id": int(project.id)},
                "different",
            )
        assert exc.value.status_code == 403


def test_service_slug_resolution_requires_explicit_organization() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _project(session, "first", "news")
        with pytest.raises(HTTPException) as exc:
            resolve_project_by_slug(
                session,
                {"type": "service", "organization_id": None},
                "news",
            )
        assert exc.value.status_code == 400
