"""GeocodeAgent compatibility values must match project ownership."""

from __future__ import annotations

import pytest
from agate_runtime.context import AgateEnvContext
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    Stylebook,
)
from sqlmodel import Session, SQLModel, create_engine


def test_geocode_cache_inherits_project_stylebook_and_rejects_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Import after agate_runtime initializes its node registry to avoid its compatibility cycle.
    from agate_nodes.geocode_agent.runner import attach_geocode_cache_bundle

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        organization = BackfieldOrganization(name="Org", slug="geocode-runtime")
        session.add(organization)
        session.flush()
        assigned = Stylebook(
            organization_id=int(organization.id),
            name="Assigned",
            slug="assigned",
            is_default=True,
        )
        other = Stylebook(
            organization_id=int(organization.id),
            name="Other",
            slug="other",
        )
        session.add(assigned)
        session.add(other)
        session.flush()
        workspace = BackfieldWorkspace(
            organization_id=int(organization.id),
            stylebook_id=int(assigned.id),
            name="Workspace",
            slug="workspace",
        )
        session.add(workspace)
        session.flush()
        project = BackfieldProject(
            organization_id=int(organization.id),
            workspace_id=int(workspace.id),
            stylebook_id=int(assigned.id),
            name="Project",
            slug="project",
        )
        session.add(project)
        session.commit()
        project_id = int(project.id)
        assigned_id = int(assigned.id)
        other_id = int(other.id)

    monkeypatch.setenv("BACKFIELD_PROJECT_ID", str(project_id))
    monkeypatch.setattr("backfield_db.session.get_engine", lambda: engine)

    inherited_context = AgateEnvContext()
    attach_geocode_cache_bundle(
        inherited_context,
        use_cache=True,
        stylebook_id=None,
    )
    assert "geocode_cache_bundle" in inherited_context.metadata

    matching_context = AgateEnvContext()
    attach_geocode_cache_bundle(
        matching_context,
        use_cache=True,
        stylebook_id=assigned_id,
    )
    assert "geocode_cache_bundle" in matching_context.metadata

    with pytest.raises(ValueError, match="does not match"):
        attach_geocode_cache_bundle(
            AgateEnvContext(),
            use_cache=True,
            stylebook_id=other_id,
        )
