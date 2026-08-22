"""Project creation pins a chosen Stylebook, or the selected workspace's default."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass

import pytest
from api.deps import get_session
from api.main import app
from backfield_auth import create_session_token
from backfield_db import (
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldProject,
    BackfieldUser,
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


def _session_client(
    ownership_fixture: ProjectOwnershipFixture,
    *,
    org_role: str,
) -> TestClient:
    """Client for a browser session in the fixture's organization with no workspace grants."""
    email = f"{org_role}@example.com"
    with Session(ownership_fixture.engine) as session:
        user = BackfieldUser(email=email, password_hash="unused")
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = int(user.id)
        session.add(
            BackfieldOrganizationMembership(
                user_id=user_id,
                organization_id=ownership_fixture.organization_id,
                role=org_role,
            )
        )
        session.commit()
    token = create_session_token(
        user_id=user_id,
        email=email,
        projects=[],
        organization_id=ownership_fixture.organization_id,
        org_role=org_role,
    )
    return TestClient(app, cookies={"session": token})


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
    assert response.json()["workspace_stylebook_id"] == ownership_fixture.replacement_stylebook_id
    with Session(ownership_fixture.engine) as session:
        project = session.get(BackfieldProject, project_id)
        assert project is not None
        assert project.stylebook_id == ownership_fixture.original_stylebook_id


def test_project_create_accepts_an_explicit_stylebook(
    ownership_fixture: ProjectOwnershipFixture,
) -> None:
    response = ownership_fixture.client.post(
        "/projects",
        json={
            "name": "Chosen project",
            "slug": "chosen-project",
            "workspace_id": ownership_fixture.workspace_id,
            "stylebook_id": ownership_fixture.replacement_stylebook_id,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stylebook_id"] == ownership_fixture.replacement_stylebook_id
    assert body["stylebook_name"] == "Replacement"
    assert body["stylebook_slug"] == "replacement"
    with Session(ownership_fixture.engine) as session:
        project = session.get(BackfieldProject, int(body["id"]))
        assert project is not None
        assert project.stylebook_id == ownership_fixture.replacement_stylebook_id


def test_workspace_stylebook_fields_report_the_workspace_not_the_project(
    ownership_fixture: ProjectOwnershipFixture,
) -> None:
    body = ownership_fixture.client.post(
        "/projects",
        json={
            "name": "Divergent project",
            "slug": "divergent-project",
            "workspace_id": ownership_fixture.workspace_id,
            "stylebook_id": ownership_fixture.replacement_stylebook_id,
        },
    ).json()

    response = ownership_fixture.client.get(f"/projects/{int(body['id'])}")

    assert response.status_code == 200
    project = response.json()
    assert project["stylebook_id"] == ownership_fixture.replacement_stylebook_id
    assert project["workspace_stylebook_id"] == ownership_fixture.original_stylebook_id
    assert project["workspace_stylebook_name"] == "Original"
    assert project["workspace_stylebook_slug"] == "original"


def _foreign_stylebook_id(engine: Engine) -> int:
    with Session(engine) as session:
        other_org = BackfieldOrganization(name="Other Org", slug="other-org")
        session.add(other_org)
        session.flush()
        foreign = Stylebook(
            organization_id=int(other_org.id),
            name="Foreign",
            slug="foreign",
            is_default=True,
        )
        session.add(foreign)
        session.commit()
        session.refresh(foreign)
        return int(foreign.id)


def test_service_token_cannot_assign_a_stylebook_from_another_organization(
    ownership_fixture: ProjectOwnershipFixture,
) -> None:
    """Service tokens may omit an organization, so the workspace supplies the only scope."""
    response = ownership_fixture.client.post(
        "/projects",
        json={
            "name": "Cross org project",
            "slug": "cross-org-project",
            "workspace_id": ownership_fixture.workspace_id,
            "stylebook_id": _foreign_stylebook_id(ownership_fixture.engine),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Stylebook not found in this organization"


def test_session_admin_cannot_assign_a_stylebook_from_another_organization(
    ownership_fixture: ProjectOwnershipFixture,
) -> None:
    foreign_stylebook_id = _foreign_stylebook_id(ownership_fixture.engine)
    client = _session_client(ownership_fixture, org_role="org_admin")

    response = client.post(
        "/projects",
        json={
            "name": "Cross org project",
            "slug": "cross-org-project",
            "workspace_id": ownership_fixture.workspace_id,
            "stylebook_id": foreign_stylebook_id,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Stylebook not found in this organization"


def test_workspace_access_is_checked_before_the_requested_stylebook(
    ownership_fixture: ProjectOwnershipFixture,
) -> None:
    """A member outside the workspace is refused without learning anything about Stylebooks."""
    client = _session_client(ownership_fixture, org_role="member")

    response = client.post(
        "/projects",
        json={
            "name": "No membership",
            "slug": "no-membership",
            "workspace_id": ownership_fixture.workspace_id,
            "stylebook_id": 99_999,
        },
    )

    assert response.status_code == 403
    assert "workspace" in response.json()["detail"].lower()


def test_project_create_rejects_an_unknown_stylebook(
    ownership_fixture: ProjectOwnershipFixture,
) -> None:
    response = ownership_fixture.client.post(
        "/projects",
        json={
            "name": "Missing stylebook project",
            "slug": "missing-stylebook-project",
            "workspace_id": ownership_fixture.workspace_id,
            "stylebook_id": 99_999,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Stylebook not found in this organization"


@pytest.mark.parametrize(
    ("field_name", "body_extra"),
    [
        ("omitted", {}),
        ("null", {"stylebook_id": None}),
        ("workspace default", {"stylebook_id": "__workspace_default__"}),
    ],
)
def test_project_create_falls_back_to_the_workspace_default(
    ownership_fixture: ProjectOwnershipFixture,
    field_name: str,
    body_extra: dict[str, object],
) -> None:
    """Omitted, explicitly null, and explicitly-the-default all land on the workspace default."""
    body: dict[str, object] = {
        "name": f"Fallback {field_name}",
        "slug": f"fallback-{field_name.replace(' ', '-')}",
        "workspace_id": ownership_fixture.workspace_id,
        **body_extra,
    }
    if body.get("stylebook_id") == "__workspace_default__":
        body["stylebook_id"] = ownership_fixture.original_stylebook_id

    response = ownership_fixture.client.post("/projects", json=body)

    assert response.status_code == 200, response.text
    assert response.json()["stylebook_id"] == ownership_fixture.original_stylebook_id


def test_project_list_reports_the_workspace_stylebook_separately(
    ownership_fixture: ProjectOwnershipFixture,
) -> None:
    """The list loop resolves both Stylebooks, not just the detail endpoint."""
    ownership_fixture.client.post(
        "/projects",
        json={
            "name": "Listed project",
            "slug": "listed-project",
            "workspace_id": ownership_fixture.workspace_id,
            "stylebook_id": ownership_fixture.replacement_stylebook_id,
        },
    )

    response = ownership_fixture.client.get("/projects")

    assert response.status_code == 200
    listed = [row for row in response.json() if row["slug"] == "listed-project"]
    assert len(listed) == 1
    assert listed[0]["stylebook_id"] == ownership_fixture.replacement_stylebook_id
    assert listed[0]["workspace_stylebook_id"] == ownership_fixture.original_stylebook_id


def test_project_list_survives_one_broken_workspace_stylebook(
    ownership_fixture: ProjectOwnershipFixture,
) -> None:
    """Compatibility fields degrade to null; one bad row must not fail the whole list."""
    healthy = ownership_fixture.client.post(
        "/projects",
        json={
            "name": "Healthy project",
            "slug": "healthy-project",
            "workspace_id": ownership_fixture.workspace_id,
        },
    )
    assert healthy.status_code == 200
    broken = ownership_fixture.client.post(
        "/projects",
        json={
            "name": "Broken workspace project",
            "slug": "broken-workspace-project",
            "workspace_id": ownership_fixture.workspace_id,
        },
    )
    assert broken.status_code == 200
    broken_id = int(broken.json()["id"])
    missing = ownership_fixture.client.post(
        "/projects",
        json={
            "name": "Missing workspace project",
            "slug": "missing-workspace-project",
            "workspace_id": ownership_fixture.workspace_id,
        },
    )
    assert missing.status_code == 200
    missing_id = int(missing.json()["id"])
    with Session(ownership_fixture.engine) as session:
        orphan = BackfieldWorkspace(
            organization_id=ownership_fixture.organization_id,
            stylebook_id=999_999,
            name="Orphan",
            slug="orphan",
        )
        session.add(orphan)
        session.commit()
        session.refresh(orphan)
        project = session.get(BackfieldProject, broken_id)
        assert project is not None
        project.workspace_id = int(orphan.id)
        session.add(project)
        orphaned = session.get(BackfieldProject, missing_id)
        assert orphaned is not None
        orphaned.workspace_id = 999_999
        session.add(orphaned)
        session.commit()

    response = ownership_fixture.client.get("/projects")

    assert response.status_code == 200
    rows = {row["slug"]: row for row in response.json()}
    assert rows["healthy-project"]["workspace_stylebook_id"] == (
        ownership_fixture.original_stylebook_id
    )
    assert rows["broken-workspace-project"]["workspace_stylebook_id"] is None
    assert rows["broken-workspace-project"]["workspace_stylebook_name"] is None
    assert rows["broken-workspace-project"]["workspace_stylebook_slug"] is None
    assert rows["missing-workspace-project"]["workspace_stylebook_id"] is None
    # The project's own Stylebook is unaffected by the broken workspace row.
    assert rows["broken-workspace-project"]["stylebook_id"] == (
        ownership_fixture.original_stylebook_id
    )


def test_project_patch_cannot_reassign_the_stylebook(
    ownership_fixture: ProjectOwnershipFixture,
) -> None:
    """Reassignment is intentionally unsupported; an unknown field must not take effect."""
    created = ownership_fixture.client.post(
        "/projects",
        json={
            "name": "Fixed project",
            "slug": "fixed-project",
            "workspace_id": ownership_fixture.workspace_id,
        },
    ).json()

    patched = ownership_fixture.client.patch(
        f"/projects/{int(created['id'])}",
        json={"stylebook_id": ownership_fixture.replacement_stylebook_id},
    )

    assert patched.status_code == 200
    assert patched.json()["stylebook_id"] == ownership_fixture.original_stylebook_id
    with Session(ownership_fixture.engine) as session:
        project = session.get(BackfieldProject, int(created["id"]))
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
                    {"id": "in", "type": "TextInput", "params": {"text": "hello"}},
                    {"id": "pe", "type": "PlaceExtract", "params": {}},
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
                "edges": [
                    {"source": "in", "target": "pe"},
                    {"source": "pe", "target": "geo"},
                    {"source": "geo", "target": "out"},
                ],
            },
        },
    )

    assert response.status_code == 200, response.text
    by_type = {node["type"]: node["params"] for node in response.json()["spec"]["nodes"]}
    assert by_type["GeocodeAgent"] == {
        "stylebook_id": ownership_fixture.original_stylebook_id,
    }
    assert by_type["DBOutput"] == {
        "stylebook_id": ownership_fixture.original_stylebook_id,
    }


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
