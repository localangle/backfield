"""Project slug uniqueness follows organization tenancy."""

from __future__ import annotations

import pytest
from backfield_db import BackfieldOrganization, BackfieldProject, BackfieldWorkspace, Stylebook
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine


def _organization_scope(session: Session, slug: str) -> tuple[int, int, int]:
    organization = BackfieldOrganization(name=slug.title(), slug=slug)
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
    return int(organization.id), int(stylebook.id), int(workspace.id)


def test_project_slug_can_repeat_across_organizations() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        first = _organization_scope(session, "first")
        second = _organization_scope(session, "second")
        for organization_id, stylebook_id, workspace_id in (first, second):
            session.add(
                BackfieldProject(
                    organization_id=organization_id,
                    stylebook_id=stylebook_id,
                    workspace_id=workspace_id,
                    name="News",
                    slug="news",
                )
            )
        session.commit()


def test_project_slug_conflicts_inside_one_organization() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        organization_id, stylebook_id, workspace_id = _organization_scope(session, "first")
        session.add(
            BackfieldProject(
                organization_id=organization_id,
                stylebook_id=stylebook_id,
                workspace_id=workspace_id,
                name="One",
                slug="news",
            )
        )
        session.commit()
        session.add(
            BackfieldProject(
                organization_id=organization_id,
                stylebook_id=stylebook_id,
                workspace_id=workspace_id,
                name="Two",
                slug="news",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
