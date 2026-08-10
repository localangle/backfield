"""Shared in-memory database fixtures for backfield-events tests."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from backfield_db import (
    AgateGraph,
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWebhookEndpoint,
    BackfieldWebhookSubscription,
    BackfieldWorkspace,
    Stylebook,
)
from backfield_events.contracts import RUN_COMPLETED_EVENT
from sqlmodel import Session, SQLModel, create_engine


@dataclass
class Tenancy:
    organization: BackfieldOrganization
    project: BackfieldProject
    graph: AgateGraph


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def tenancy(session: Session) -> Tenancy:
    organization = BackfieldOrganization(name="Test Org", slug="test-org")
    session.add(organization)
    session.flush()
    stylebook = Stylebook(
        organization_id=int(organization.id),
        name="Test Stylebook",
        slug="test-stylebook",
        is_default=True,
    )
    session.add(stylebook)
    session.flush()
    workspace = BackfieldWorkspace(
        organization_id=int(organization.id),
        stylebook_id=int(stylebook.id),
        name="Test Workspace",
        slug="test-workspace",
    )
    session.add(workspace)
    session.flush()
    project = BackfieldProject(
        organization_id=int(organization.id),
        workspace_id=int(workspace.id),
        stylebook_id=int(stylebook.id),
        name="Test Project",
        slug="test-project",
    )
    session.add(project)
    session.flush()
    graph = AgateGraph(name="Test Flow", spec_json="{}", project_id=int(project.id))
    session.add(graph)
    session.flush()
    return Tenancy(organization=organization, project=project, graph=graph)


@pytest.fixture()
def webhooks_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKFIELD_WEBHOOKS_ENABLED", "1")


def make_run(session: Session, graph: AgateGraph, *, status: str = "running") -> AgateRun:
    run = AgateRun(graph_id=graph.id, status=status)
    session.add(run)
    session.flush()
    return run


def make_endpoint(
    session: Session,
    project: BackfieldProject,
    graph: AgateGraph,
    *,
    status: str = "active",
    outcomes: list[str] | None = None,
) -> BackfieldWebhookEndpoint:
    endpoint = BackfieldWebhookEndpoint(
        organization_id=int(project.organization_id),
        project_id=int(project.id),
        name="Receiver",
        url_encrypted="not-a-real-ciphertext",
        display_host="hooks.example.com",
        signing_secret_encrypted="not-a-real-ciphertext",
        status=status,
    )
    session.add(endpoint)
    session.flush()
    session.add(
        BackfieldWebhookSubscription(
            endpoint_id=endpoint.id,
            event_type=RUN_COMPLETED_EVENT,
            graph_id=graph.id,
            outcomes_json=json.dumps(outcomes) if outcomes is not None else None,
        )
    )
    session.flush()
    return endpoint
