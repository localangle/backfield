"""Tests for Phase A connection KG offline migration."""

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
            description="Ada works for Acme",
        )
    )
    session.commit()
    report = migrate_connections_kg_phase_a(session, inventory_only=True)
    assert report.connection_total == 1
    assert report.remapped == 0
    assert session.exec(select(StylebookConnectionEvidence)).first() is None


def test_represented_by_swap_and_merge_with_evidence() -> None:
    session = _session()
    project_id, stylebook_id = _project(session)
    lawyer = _person(session, stylebook_id, "Lawyer")
    client = _person(session, stylebook_id, "Client")
    # Client represented_by Lawyer  →  Lawyer represents Client
    session.add(
        StylebookConnection(
            project_id=project_id,
            stylebook_id=stylebook_id,
            from_entity_type="person",
            from_entity_id=client,
            to_entity_type="person",
            to_entity_id=lawyer,
            nature="represented_by",
            description="Client is represented by Lawyer",
            evidence_json={
                "source": "dboutput_auto_connections",
                "quote": "represented by Lawyer",
                "reason": "explicit",
                "confidence": 0.95,
                "article_id": 101,
            },
        )
    )
    session.add(
        StylebookConnection(
            project_id=project_id,
            stylebook_id=stylebook_id,
            from_entity_type="person",
            from_entity_id=lawyer,
            to_entity_type="person",
            to_entity_id=client,
            nature="represents",
            description="Lawyer represents Client",
            evidence_json={
                "source": "dboutput_auto_connections",
                "quote": "Lawyer represents Client",
                "reason": "explicit",
                "confidence": 0.96,
                "article_id": 102,
            },
        )
    )
    session.commit()

    report = migrate_connections_kg_phase_a(session, apply=True)
    assert report.remapped == 1
    assert report.duplicates_deleted == 1
    assert report.evidence_created == 2

    rows = list(session.exec(select(StylebookConnection)).all())
    assert len(rows) == 1
    survivor = rows[0]
    assert survivor.nature == "represents"
    assert survivor.from_entity_id == lawyer
    assert survivor.to_entity_id == client
    assert survivor.description is None

    evidence = list(session.exec(select(StylebookConnectionEvidence)).all())
    assert len(evidence) == 2
    article_ids = {e.article_id for e in evidence}
    assert article_ids == {101, 102}


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
            description="Team of the school",
        )
    )
    session.commit()
    report = migrate_connections_kg_phase_a(session, apply=True)
    assert report.remapped == 1
    row = session.exec(select(StylebookConnection)).one()
    assert row.nature == "team_of"
    evidence = session.exec(select(StylebookConnectionEvidence)).one()
    assert evidence.source == "legacy_manual"
    assert evidence.description == "Team of the school"


def test_quarantine_no_relationship_description() -> None:
    session = _session()
    project_id, stylebook_id = _project(session)
    a = _org(session, stylebook_id, "A")
    b = _org(session, stylebook_id, "B")
    session.add(
        StylebookConnection(
            project_id=project_id,
            stylebook_id=stylebook_id,
            from_entity_type="organization",
            from_entity_id=a,
            to_entity_type="organization",
            to_entity_id=b,
            nature=None,
            description="No valid organization-to-organization relationship can be extracted",
        )
    )
    session.commit()
    report = migrate_connections_kg_phase_a(session, apply=True)
    assert report.quarantined == 1
    assert session.exec(select(StylebookConnection)).first() is None


def test_dry_run_reports_without_writing_evidence() -> None:
    session = _session()
    project_id, stylebook_id = _project(session)
    person = _person(session, stylebook_id, "Pat")
    org = _org(session, stylebook_id, "City")
    session.add(
        StylebookConnection(
            project_id=project_id,
            stylebook_id=stylebook_id,
            from_entity_type="person",
            from_entity_id=person,
            to_entity_type="organization",
            to_entity_id=org,
            nature="works_at",
            description="Pat works at City",
        )
    )
    session.add(
        StylebookConnection(
            project_id=project_id,
            stylebook_id=stylebook_id,
            from_entity_type="person",
            from_entity_id=person,
            to_entity_type="organization",
            to_entity_id=org,
            nature="works_for",
            description="Pat works for City hall",
        )
    )
    session.commit()
    report = migrate_connections_kg_phase_a(session, apply=False)
    assert report.remapped >= 1
    assert report.duplicates_deleted == 1
    assert report.evidence_created == 2
    assert session.exec(select(StylebookConnectionEvidence)).first() is None
    assert len(list(session.exec(select(StylebookConnection)).all())) == 2


def test_cli_migrate_connection_kg_json(monkeypatch, capsys) -> None:
    from backfield_cli.main import main
    from backfield_entities.connections.migrate_kg_phase_a import ConnectionKgMigrateReport

    def _fake_migrate(session, **kwargs):
        return ConnectionKgMigrateReport(
            apply=False,
            inventory_only=True,
            connection_total=3,
            null_nature_count=1,
        )

    monkeypatch.setattr(
        "backfield_cli.migrate_connection_kg.migrate_connections_kg_phase_a",
        _fake_migrate,
    )
    monkeypatch.setattr(
        "backfield_cli.migrate_connection_kg.get_engine",
        lambda: create_engine("sqlite://"),
    )
    assert main(["migrate-connection-kg", "--inventory-only", "--json"]) == 0
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["connection_total"] == 3
    assert payload["inventory_only"] is True
