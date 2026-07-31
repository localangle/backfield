"""Project creation pins the selected workspace's Stylebook."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass

import pytest
from api.deps import get_session
from api.main import app
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    Stylebook,
)
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine


@dataclass(frozen=True)
class ProjectOwnershipFixture:
    client: TestClient
    engine: Engine
    organization_id: int
    workspace_id: int
    original_stylebook_id: int
    replacement_stylebook_id: int


@pytest.fixture
def ownership_fixture(tmp_path) -> Generator[ProjectOwnershipFixture, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'project-stylebook.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        organization = BackfieldOrganization(name="News Org", slug="news-org")
        session.add(organization)
        session.flush()
        original = Stylebook(
            organization_id=int(organization.id),
            name="Original",
            slug="original",
            is_default=True,
        )
        replacement = Stylebook(
            organization_id=int(organization.id),
            name="Replacement",
            slug="replacement",
            is_default=False,
        )
        session.add(original)
        session.add(replacement)
        session.flush()
        workspace = BackfieldWorkspace(
            organization_id=int(organization.id),
            stylebook_id=int(original.id),
            name="Newsroom",
            slug="newsroom",
        )
        session.add(workspace)
        session.commit()
        session.refresh(organization)
        session.refresh(original)
        session.refresh(replacement)
        session.refresh(workspace)
        organization_id = int(organization.id)
        workspace_id = int(workspace.id)
        original_stylebook_id = int(original.id)
        replacement_stylebook_id = int(replacement.id)

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        yield ProjectOwnershipFixture(
            client=TestClient(app, headers={"Authorization": "Bearer backfield-dev"}),
            engine=engine,
            organization_id=organization_id,
            workspace_id=workspace_id,
            original_stylebook_id=original_stylebook_id,
            replacement_stylebook_id=replacement_stylebook_id,
        )
    finally:
        app.dependency_overrides.clear()


def test_project_create_requires_workspace(
    ownership_fixture: ProjectOwnershipFixture,
) -> None:
    missing_workspace = ownership_fixture.client.post(
        "/projects",
        json={
            "name": "Missing workspace",
        },
    )
    assert missing_workspace.status_code == 422


def test_project_create_copies_workspace_stylebook_and_exposes_direct_fields(
    ownership_fixture: ProjectOwnershipFixture,
) -> None:
    response = ownership_fixture.client.post(
        "/projects",
        json={
            "name": "Pinned project",
            "slug": "pinned-project",
            "workspace_id": ownership_fixture.workspace_id,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stylebook_id"] == ownership_fixture.original_stylebook_id
    assert body["stylebook_name"] == "Original"
    assert body["stylebook_slug"] == "original"
    assert body["workspace_stylebook_id"] == ownership_fixture.original_stylebook_id
    with Session(ownership_fixture.engine) as session:
        project = session.get(BackfieldProject, int(body["id"]))
        assert project is not None
        assert project.stylebook_id == ownership_fixture.original_stylebook_id


def test_workspace_stylebook_change_does_not_mutate_existing_project(
    ownership_fixture: ProjectOwnershipFixture,
) -> None:
    created = ownership_fixture.client.post(
        "/projects",
        json={
            "name": "Stable project",
            "slug": "stable-project",
            "workspace_id": ownership_fixture.workspace_id,
        },
    )
    assert created.status_code == 200
    project_id = int(created.json()["id"])

    with Session(ownership_fixture.engine) as session:
        workspace = session.get(BackfieldWorkspace, ownership_fixture.workspace_id)
        assert workspace is not None
        workspace.stylebook_id = ownership_fixture.replacement_stylebook_id
        session.add(workspace)
        session.commit()

    response = ownership_fixture.client.get(f"/projects/{project_id}")
    assert response.status_code == 200
    assert response.json()["stylebook_id"] == ownership_fixture.original_stylebook_id
    assert response.json()["workspace_stylebook_id"] == ownership_fixture.original_stylebook_id
    with Session(ownership_fixture.engine) as session:
        project = session.get(BackfieldProject, project_id)
        assert project is not None
        assert project.stylebook_id == ownership_fixture.original_stylebook_id


def test_graph_write_normalizes_runtime_nodes_to_project_stylebook(
    ownership_fixture: ProjectOwnershipFixture,
) -> None:
    project = ownership_fixture.client.post(
        "/projects",
        json={
            "name": "Normalized project",
            "slug": "normalized-project",
            "workspace_id": ownership_fixture.workspace_id,
        },
    ).json()

    response = ownership_fixture.client.post(
        "/graphs",
        json={
            "name": "Normalized flow",
            "project_id": project["id"],
            "spec": {
                "name": "normalized",
                "nodes": [
                    {
                        "id": "geo",
                        "type": "GeocodeAgent",
                        "params": {"stylebookId": ownership_fixture.original_stylebook_id},
                    },
                    {
                        "id": "out",
                        "type": "DBOutput",
                        "params": {"stylebook_id": ownership_fixture.original_stylebook_id},
                    },
                ],
                "edges": [],
            },
        },
    )

    assert response.status_code == 200, response.text
    params = [node["params"] for node in response.json()["spec"]["nodes"]]
    assert params == [
        {"stylebook_id": ownership_fixture.original_stylebook_id},
        {"stylebook_id": ownership_fixture.original_stylebook_id},
    ]


def test_graph_create_and_update_reject_conflicting_runtime_stylebook(
    ownership_fixture: ProjectOwnershipFixture,
) -> None:
    project = ownership_fixture.client.post(
        "/projects",
        json={
            "name": "Strict project",
            "slug": "strict-project",
            "workspace_id": ownership_fixture.workspace_id,
        },
    ).json()
    mismatch_spec = {
        "name": "mismatch",
        "nodes": [
            {
                "id": "out",
                "type": "DBOutput",
                "params": {"stylebook_id": ownership_fixture.replacement_stylebook_id},
            },
        ],
        "edges": [],
    }

    rejected_create = ownership_fixture.client.post(
        "/graphs",
        json={
            "name": "Rejected flow",
            "project_id": project["id"],
            "spec": mismatch_spec,
        },
    )
    assert rejected_create.status_code == 400
    assert "does not match" in rejected_create.json()["detail"]

    created = ownership_fixture.client.post(
        "/graphs",
        json={
            "name": "Accepted flow",
            "project_id": project["id"],
            "spec": {"name": "accepted", "nodes": [], "edges": []},
        },
    )
    assert created.status_code == 200
    rejected_update = ownership_fixture.client.put(
        f"/graphs/{created.json()['id']}",
        json={
            "name": "Rejected update",
            "project_id": project["id"],
            "spec": mismatch_spec,
        },
    )
    assert rejected_update.status_code == 400
    assert "does not match" in rejected_update.json()["detail"]
