"""Read-only tenancy preflight audit coverage."""

from __future__ import annotations

import json

from backfield_db import (
    AgateGraph,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    Stylebook,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateLocation,
    SubstrateOrganization,
    SubstratePerson,
)
from backfield_db.tenancy_audit import (
    ProjectAuditRow,
    TenancyBlockerCode,
    _duplicate_project_slug_blockers,
    _load_projects,
    audit_tenancy,
)
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine


def _engine(*, legacy_nullable_project_ownership: bool = False):
    engine = create_engine("sqlite://")
    workspace_column = BackfieldProject.__table__.c.workspace_id
    stylebook_column = BackfieldProject.__table__.c.stylebook_id
    if legacy_nullable_project_ownership:
        workspace_column.nullable = True
        stylebook_column.nullable = True
    try:
        SQLModel.metadata.create_all(engine)
    finally:
        workspace_column.nullable = False
        stylebook_column.nullable = False
    return engine


def test_project_audit_rows_load_before_stylebook_column_exists() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE backfield_project (
                    id INTEGER PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    workspace_id INTEGER,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO backfield_project
                    (id, organization_id, workspace_id, name, slug)
                VALUES (1, 10, NULL, 'Legacy', 'legacy')
                """
            )
        )

    with Session(engine) as session:
        projects = _load_projects(session)

    assert len(projects) == 1
    assert projects[0].id == 1
    assert projects[0].stylebook_id is None


def test_tenancy_audit_clean_report_is_read_only() -> None:
    engine = _engine()
    with Session(engine) as session:
        organization = BackfieldOrganization(name="One", slug="audit-clean")
        session.add(organization)
        session.flush()
        stylebook = Stylebook(
            organization_id=int(organization.id),
            name="Default",
            slug="default",
            is_default=True,
        )
        session.add(stylebook)
        session.flush()
        workspace = BackfieldWorkspace(
            organization_id=int(organization.id),
            stylebook_id=int(stylebook.id),
            name="Workspace",
            slug="workspace",
        )
        session.add(workspace)
        session.flush()
        project = BackfieldProject(
            organization_id=int(organization.id),
            workspace_id=int(workspace.id),
            stylebook_id=int(stylebook.id),
            name="Project",
            slug="audit-clean-project",
        )
        session.add(project)
        session.flush()
        session.add(
            AgateGraph(
                project_id=int(project.id),
                name="Graph",
                spec_json=json.dumps(
                    {
                        "nodes": [
                            {
                                "id": "output",
                                "params": {"stylebook_id": int(stylebook.id)},
                            }
                        ]
                    }
                ),
            )
        )
        session.commit()

        report = audit_tenancy(session)

        assert report.ok is True
        assert report.blocker_count == 0
        assert report.blockers == []
        assert not session.new
        assert not session.dirty
        assert not session.deleted


def test_tenancy_audit_reports_cross_layer_blockers() -> None:
    engine = _engine(legacy_nullable_project_ownership=True)
    with Session(engine) as session:
        organization_one = BackfieldOrganization(name="One", slug="audit-one")
        organization_two = BackfieldOrganization(name="Two", slug="audit-two")
        organization_three = BackfieldOrganization(name="Three", slug="audit-three")
        session.add_all([organization_one, organization_two, organization_three])
        session.flush()
        stylebook_one = Stylebook(
            organization_id=int(organization_one.id),
            name="One",
            slug="one",
            is_default=True,
        )
        stylebook_one_extra = Stylebook(
            organization_id=int(organization_one.id),
            name="One Extra",
            slug="one-extra",
            is_default=False,
        )
        stylebook_two = Stylebook(
            organization_id=int(organization_two.id),
            name="Two",
            slug="two",
            is_default=True,
        )
        session.add_all([stylebook_one, stylebook_one_extra, stylebook_two])
        session.flush()
        workspace_one = BackfieldWorkspace(
            organization_id=int(organization_one.id),
            stylebook_id=int(stylebook_one.id),
            name="One",
            slug="one",
        )
        workspace_cross_stylebook = BackfieldWorkspace(
            organization_id=int(organization_one.id),
            stylebook_id=int(stylebook_two.id),
            name="Cross Stylebook",
            slug="cross-stylebook",
        )
        workspace_two = BackfieldWorkspace(
            organization_id=int(organization_two.id),
            stylebook_id=int(stylebook_two.id),
            name="Two",
            slug="two",
        )
        session.add_all([workspace_one, workspace_cross_stylebook, workspace_two])
        session.flush()
        orphan = BackfieldProject(
            organization_id=int(organization_one.id),
            workspace_id=None,
            stylebook_id=None,
            name="Orphan",
            slug="audit-orphan",
        )
        cross_workspace = BackfieldProject(
            organization_id=int(organization_one.id),
            workspace_id=int(workspace_two.id),
            stylebook_id=int(stylebook_one.id),
            name="Cross Workspace",
            slug="audit-cross-workspace",
        )
        cross_stylebook = BackfieldProject(
            organization_id=int(organization_one.id),
            workspace_id=int(workspace_one.id),
            stylebook_id=int(stylebook_two.id),
            name="Cross Stylebook",
            slug="audit-cross-stylebook",
        )
        graph_project = BackfieldProject(
            organization_id=int(organization_one.id),
            workspace_id=int(workspace_one.id),
            stylebook_id=int(stylebook_one.id),
            name="Graph Project",
            slug="audit-graph-project",
        )
        unresolved = BackfieldProject(
            organization_id=int(organization_three.id),
            workspace_id=None,
            stylebook_id=None,
            name="Unresolved",
            slug="audit-unresolved",
        )
        session.add_all([orphan, cross_workspace, cross_stylebook, graph_project, unresolved])
        session.flush()
        session.add(
            AgateGraph(
                project_id=int(graph_project.id),
                name="Mixed Graph",
                spec_json=json.dumps(
                    {
                        "nodes": [
                            {
                                "id": "one-extra",
                                "params": {"stylebook_id": int(stylebook_one_extra.id)},
                            },
                            {
                                "id": "two",
                                "params": {"stylebookId": int(stylebook_two.id)},
                            },
                        ]
                    }
                ),
            )
        )
        location_canonical = StylebookLocationCanonical(
            stylebook_id=int(stylebook_two.id),
            label="Location",
            slug="location",
        )
        other_location_canonical = StylebookLocationCanonical(
            stylebook_id=int(stylebook_one_extra.id),
            label="Other Location",
            slug="other-location",
        )
        person_canonical = StylebookPersonCanonical(
            stylebook_id=int(stylebook_two.id),
            label="Person",
            slug="person",
        )
        organization_canonical = StylebookOrganizationCanonical(
            stylebook_id=int(stylebook_two.id),
            label="Organization",
            slug="organization",
        )
        session.add_all(
            [
                location_canonical,
                other_location_canonical,
                person_canonical,
                organization_canonical,
            ]
        )
        session.flush()
        session.add_all(
            [
                SubstrateLocation(
                    project_id=int(graph_project.id),
                    name=f"Location {index}",
                    normalized_name=f"location {index}",
                    canonical_link_status="linked",
                    stylebook_location_canonical_id=location_canonical.id,
                )
                for index in range(12)
            ]
        )
        session.add(
            SubstrateLocation(
                project_id=int(graph_project.id),
                name="Other Location",
                normalized_name="other location",
                canonical_link_status="linked",
                stylebook_location_canonical_id=other_location_canonical.id,
            )
        )
        session.add(
            SubstratePerson(
                project_id=int(graph_project.id),
                name="Person",
                normalized_name="person",
                canonical_link_status="linked",
                stylebook_person_canonical_id=person_canonical.id,
            )
        )
        session.add(
            SubstrateOrganization(
                project_id=int(graph_project.id),
                name="Organization",
                normalized_name="organization",
                canonical_link_status="linked",
                stylebook_organization_canonical_id=organization_canonical.id,
            )
        )
        session.commit()

        report = audit_tenancy(session)

        codes = {blocker.code for blocker in report.blockers}
        assert report.ok is False
        assert {
            TenancyBlockerCode.ORPHAN_PROJECT,
            TenancyBlockerCode.PROJECT_WORKSPACE_ORGANIZATION_MISMATCH,
            TenancyBlockerCode.WORKSPACE_STYLEBOOK_ORGANIZATION_MISMATCH,
            TenancyBlockerCode.PROJECT_STYLEBOOK_ORGANIZATION_MISMATCH,
            TenancyBlockerCode.PROJECT_STYLEBOOK_UNRESOLVED,
            TenancyBlockerCode.GRAPH_STYLEBOOK_CONFLICT,
            TenancyBlockerCode.GRAPH_MULTIPLE_STYLEBOOKS,
            TenancyBlockerCode.LINKED_CANONICAL_STYLEBOOK_MISMATCH,
        } <= codes
        linked = [
            blocker
            for blocker in report.blockers
            if blocker.code == TenancyBlockerCode.LINKED_CANONICAL_STYLEBOOK_MISMATCH
        ]
        assert {blocker.entity_type for blocker in linked} == {
            "location",
            "person",
            "organization",
        }
        assert len(linked) == 4
        location_blocker = next(
            blocker
            for blocker in linked
            if blocker.entity_type == "location"
            and blocker.stylebook_id == int(stylebook_two.id)
        )
        assert location_blocker.affected_count == 12
        assert len(location_blocker.sample_entity_ids) == 5
        assert location_blocker.sample_entity_ids == sorted(
            location_blocker.sample_entity_ids,
            key=int,
        )
        assert location_blocker.entity_id is None
        other_location_blocker = next(
            blocker
            for blocker in linked
            if blocker.entity_type == "location"
            and blocker.stylebook_id == int(stylebook_one_extra.id)
        )
        assert other_location_blocker.affected_count == 1


def test_duplicate_project_slug_audit_is_scoped_to_organization() -> None:
    rows = [
        ProjectAuditRow(
            id=1,
            organization_id=10,
            workspace_id=None,
            stylebook_id=None,
            name="A",
            slug="duplicate",
        ),
        ProjectAuditRow(
            id=2,
            organization_id=10,
            workspace_id=None,
            stylebook_id=None,
            name="B",
            slug="duplicate",
        ),
        ProjectAuditRow(
            id=3,
            organization_id=20,
            workspace_id=None,
            stylebook_id=None,
            name="C",
            slug="duplicate",
        ),
    ]

    blockers = _duplicate_project_slug_blockers(rows)

    assert len(blockers) == 1
    assert blockers[0].code == TenancyBlockerCode.DUPLICATE_PROJECT_SLUG
    assert blockers[0].organization_id == 10
