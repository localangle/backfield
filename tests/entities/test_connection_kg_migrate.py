"""Tests for Phase A connection KG offline migration (post-cutover schema)."""

from __future__ import annotations

from uuid import uuid4

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    StylebookConnection,
    StylebookConnectionEvidence,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.connections.migrate_kg_phase_a import migrate_connections_kg_phase_a
from sqlmodel import Session, SQLModel, create_engine, select

from tests.project_helpers import project_ownership_fields


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _project(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug=f"org-{uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    stylebook = ensure_default_stylebook_for_organization(session, oid)
    project = BackfieldProject(
        **project_ownership_fields(session, oid),
        name="News",
        slug=f"news-{uuid4().hex[:8]}",
        organization_id=oid,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return int(project.id), int(stylebook.id)  # type: ignore[arg-type]


def _person(session: Session, stylebook_id: int, label: str) -> str:
    row = StylebookPersonCanonical(
        id=str(uuid4()),
        stylebook_id=stylebook_id,
        label=label,
        slug=label.lower().replace(" ", "-"),
    )
    session.add(row)
    session.commit()
    return str(row.id)


def _org(session: Session, stylebook_id: int, label: str) -> str:
    row = StylebookOrganizationCanonical(
        id=str(uuid4()),
        stylebook_id=stylebook_id,
        label=label,
        slug=label.lower().replace(" ", "-"),
    )
    session.add(row)
    session.commit()
    return str(row.id)


def test_inventory_only_does_not_mutate() -> None:
    session = _session()
    project_id, stylebook_id = _project(session)
    person = _person(session, stylebook_id, "Ada")
    org = _org(session, stylebook_id, "Acme")
    session.add(
        StylebookConnection(
            project_id=project_id,
            stylebook_id=stylebook_id,
            from_entity_type="person",
            from_entity_id=person,
            to_entity_type="organization",
            to_entity_id=org,
            nature="works_for",
        )
    )
    unbackfilled = StylebookConnection(
        project_id=project_id,
        stylebook_id=None,
        from_entity_type="person",
        from_entity_id=person,
        to_entity_type="organization",
        to_entity_id=org,
        nature="member_of",
    )
    session.add(unbackfilled)
    session.commit()
    report = migrate_connections_kg_phase_a(session, inventory_only=True)
    assert report.connection_total == 2
    assert report.remapped == 0
    assert report.stylebook_id_backfilled == 1
    # The in-memory backfill of stylebook_id must be rolled back, not persisted.
    session.refresh(unbackfilled)
    assert unbackfilled.stylebook_id is None


def test_represented_by_swap_and_merge() -> None:
    session = _session()
    project_id, stylebook_id = _project(session)
    lawyer = _person(session, stylebook_id, "Lawyer")
    client = _person(session, stylebook_id, "Client")
    a = StylebookConnection(
        project_id=project_id,
        stylebook_id=stylebook_id,
        from_entity_type="person",
        from_entity_id=client,
        to_entity_type="person",
        to_entity_id=lawyer,
        nature="represented_by",
    )
    b = StylebookConnection(
        project_id=project_id,
        stylebook_id=stylebook_id,
        from_entity_type="person",
        from_entity_id=lawyer,
        to_entity_type="person",
        to_entity_id=client,
        nature="represents",
    )
    session.add(a)
    session.add(b)
    session.commit()
    session.refresh(a)
    session.refresh(b)
    session.add(
        StylebookConnectionEvidence(
            connection_id=int(a.id),  # type: ignore[arg-type]
            article_id=101,
            quote="represented by Lawyer",
            source="dboutput_auto_connections",
        )
    )
    session.add(
        StylebookConnectionEvidence(
            connection_id=int(b.id),  # type: ignore[arg-type]
            article_id=102,
            quote="Lawyer represents Client",
            source="dboutput_auto_connections",
        )
    )
    session.commit()

    report = migrate_connections_kg_phase_a(session, apply=True)
    assert report.remapped == 1
    assert report.duplicates_deleted == 1

    rows = list(session.exec(select(StylebookConnection)).all())
    assert len(rows) == 1
    survivor = rows[0]
    assert survivor.nature == "represents"
    assert survivor.from_entity_id == lawyer
    assert survivor.to_entity_id == client

    evidence = list(session.exec(select(StylebookConnectionEvidence)).all())
    assert len(evidence) == 2
    assert {e.article_id for e in evidence} == {101, 102}


def test_plays_for_org_org_becomes_team_of() -> None:
    session = _session()
    project_id, stylebook_id = _project(session)
    team = _org(session, stylebook_id, "Varsity Basketball")
    school = _org(session, stylebook_id, "Central High")
    session.add(
        StylebookConnection(
            project_id=project_id,
            stylebook_id=stylebook_id,
            from_entity_type="organization",
            from_entity_id=team,
            to_entity_type="organization",
            to_entity_id=school,
            nature="plays_for",
        )
    )
    session.commit()
    report = migrate_connections_kg_phase_a(session, apply=True)
    assert report.remapped == 1
    row = session.exec(select(StylebookConnection)).one()
    assert row.nature == "team_of"


def test_quarantine_no_relationship_evidence() -> None:
    session = _session()
    project_id, stylebook_id = _project(session)
    a = _org(session, stylebook_id, "A")
    b = _org(session, stylebook_id, "B")
    conn = StylebookConnection(
        project_id=project_id,
        stylebook_id=stylebook_id,
        from_entity_type="organization",
        from_entity_id=a,
        to_entity_type="organization",
        to_entity_id=b,
        nature=None,
    )
    session.add(conn)
    session.commit()
    session.refresh(conn)
    session.add(
        StylebookConnectionEvidence(
            connection_id=int(conn.id),  # type: ignore[arg-type]
            description="No valid organization-to-organization relationship can be extracted",
            source="legacy_manual",
        )
    )
    session.commit()
    report = migrate_connections_kg_phase_a(session, apply=True)
    assert report.quarantined == 1
    assert session.exec(select(StylebookConnection)).first() is None
