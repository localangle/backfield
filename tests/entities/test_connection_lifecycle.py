"""Tests for connection soft-close on delete and orphan repair."""

from __future__ import annotations

from uuid import uuid4

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    StylebookConnection,
    StylebookConnectionEvidence,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.connections.lifecycle import (
    close_open_connections_for_canonical,
    repair_orphan_open_connections,
)
from sqlmodel import Session, SQLModel, create_engine, select

from tests.project_helpers import project_ownership_fields


def _seed(session: Session) -> tuple[int, int, int]:
    org = BackfieldOrganization(name="Org", slug="org-conn-lifecycle")
    session.add(org)
    session.commit()
    session.refresh(org)
    org_id = int(org.id)  # type: ignore[arg-type]
    stylebook = ensure_default_stylebook_for_organization(session, org_id)
    stylebook_id = int(stylebook.id)  # type: ignore[arg-type]
    proj = BackfieldProject(
        **project_ownership_fields(session, org_id),
        name="News",
        slug="news",
        organization_id=org_id,
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    project_id = int(proj.id)  # type: ignore[arg-type]
    return org_id, stylebook_id, project_id


def test_close_open_connections_for_canonical_soft_closes_both_ends() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _org_id, stylebook_id, project_id = _seed(session)
        person = StylebookPersonCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="Jane Doe",
            slug="jane-doe",
        )
        org = StylebookOrganizationCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="City Council",
            slug="city-council",
            organization_type="government",
        )
        session.add(person)
        session.add(org)
        session.commit()

        from_conn = StylebookConnection(
            project_id=project_id,
            stylebook_id=stylebook_id,
            from_entity_type="person",
            from_entity_id=str(person.id),
            to_entity_type="organization",
            to_entity_id=str(org.id),
            nature="works_for",
        )
        to_conn = StylebookConnection(
            project_id=project_id,
            stylebook_id=stylebook_id,
            from_entity_type="organization",
            from_entity_id=str(org.id),
            to_entity_type="person",
            to_entity_id=str(person.id),
            nature="employs",
        )
        other = StylebookConnection(
            project_id=project_id,
            stylebook_id=stylebook_id,
            from_entity_type="organization",
            from_entity_id=str(org.id),
            to_entity_type="organization",
            to_entity_id=str(uuid4()),
            nature="related_to",
        )
        session.add(from_conn)
        session.add(to_conn)
        session.add(other)
        session.commit()

        result = close_open_connections_for_canonical(
            session,
            entity_type="person",
            canonical_id=str(person.id),
        )
        session.commit()

        assert result.closed_count == 2
        rows = {int(row.id): row for row in session.exec(select(StylebookConnection)).all()}
        assert rows[int(from_conn.id)].closed_at is not None
        assert rows[int(to_conn.id)].closed_at is not None
        assert rows[int(other.id)].closed_at is None


def test_repair_orphan_rewires_when_evidence_label_uniquely_matches() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _org_id, stylebook_id, project_id = _seed(session)
        survivor = StylebookOrganizationCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="Montini Football",
            slug="montini-football",
            organization_type="team",
        )
        loc = StylebookLocationCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="Lombard",
            slug="lombard",
        )
        session.add(survivor)
        session.add(loc)
        session.commit()

        missing_id = str(uuid4())
        conn = StylebookConnection(
            project_id=project_id,
            stylebook_id=stylebook_id,
            from_entity_type="organization",
            from_entity_id=missing_id,
            to_entity_type="location",
            to_entity_id=str(loc.id),
            nature="located_at",
        )
        session.add(conn)
        session.commit()
        session.refresh(conn)

        session.add(
            StylebookConnectionEvidence(
                connection_id=int(conn.id),
                description="team based in Lombard",
                quote="Montini Football plays in Lombard",
                reason="explicit location",
                confidence=0.9,
                source="dboutput_auto_connections",
                payload_json={
                    "from_display_name": "Montini Football",
                    "to_display_name": "Lombard",
                },
            )
        )
        session.commit()

        dry = repair_orphan_open_connections(session, stylebook_id=stylebook_id, dry_run=True)
        assert dry.rewired_count == 1
        assert dry.closed_count == 0
        assert session.exec(select(StylebookConnection)).one().from_entity_id == missing_id

        applied = repair_orphan_open_connections(
            session, stylebook_id=stylebook_id, dry_run=False
        )
        session.commit()
        assert applied.rewired_count == 1
        assert applied.closed_count == 0
        row = session.exec(select(StylebookConnection)).one()
        assert row.from_entity_id == str(survivor.id)
        assert row.to_entity_id == str(loc.id)
        assert row.closed_at is None


def test_repair_orphan_soft_closes_when_no_unique_survivor() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _org_id, stylebook_id, project_id = _seed(session)
        person = StylebookPersonCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="Alive Person",
            slug="alive-person",
        )
        session.add(person)
        session.commit()

        missing_id = str(uuid4())
        conn = StylebookConnection(
            project_id=project_id,
            stylebook_id=stylebook_id,
            from_entity_type="person",
            from_entity_id=missing_id,
            to_entity_type="person",
            to_entity_id=str(person.id),
            nature="related_to",
        )
        session.add(conn)
        session.commit()
        session.refresh(conn)
        session.add(
            StylebookConnectionEvidence(
                connection_id=int(conn.id),
                description="ghost mention",
                quote="someone mentioned",
                reason="weak",
                confidence=0.5,
                source="dboutput_auto_connections",
                payload_json={"from_display_name": "No Such Label"},
            )
        )
        session.commit()

        result = repair_orphan_open_connections(
            session, stylebook_id=stylebook_id, dry_run=False
        )
        session.commit()
        assert result.closed_count == 1
        assert result.rewired_count == 0
        assert session.exec(select(StylebookConnection)).one().closed_at is not None
