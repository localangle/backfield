"""Tests for connection rewiring during canonical merge."""

from __future__ import annotations

from uuid import uuid4

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    StylebookConnection,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstratePerson,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.connections.rewire import rewire_connections_for_canonical_merge
from backfield_entities.entities.person.merge import merge_person_canonical_into
from sqlmodel import Session, SQLModel, create_engine, select


def _seed(session: Session) -> tuple[int, int, int]:
    org = BackfieldOrganization(name="Org", slug="org-conn-rewire")
    session.add(org)
    session.commit()
    session.refresh(org)
    org_id = int(org.id)  # type: ignore[arg-type]
    stylebook = ensure_default_stylebook_for_organization(session, org_id)
    stylebook_id = int(stylebook.id)  # type: ignore[arg-type]
    proj = BackfieldProject(name="News", slug="news", organization_id=org_id)
    session.add(proj)
    session.commit()
    session.refresh(proj)
    project_id = int(proj.id)  # type: ignore[arg-type]
    return org_id, stylebook_id, project_id


def test_rewire_connections_updates_from_and_to_endpoints() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org_id, stylebook_id, project_id = _seed(session)
        source = StylebookPersonCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="Jane Source",
            slug="jane-source",
        )
        target = StylebookPersonCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="Jane Target",
            slug="jane-target",
        )
        org = StylebookOrganizationCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="City Council",
            slug="city-council",
            organization_type="government",
        )
        session.add(source)
        session.add(target)
        session.add(org)
        session.commit()

        from_conn = StylebookConnection(
            project_id=project_id,
            from_entity_type="person",
            from_entity_id=str(source.id),
            to_entity_type="organization",
            to_entity_id=str(org.id),
            nature="works_for",
        )
        to_conn = StylebookConnection(
            project_id=project_id,
            from_entity_type="organization",
            from_entity_id=str(org.id),
            to_entity_type="person",
            to_entity_id=str(source.id),
            nature="employs",
        )
        session.add(from_conn)
        session.add(to_conn)
        session.commit()

        result = rewire_connections_for_canonical_merge(
            session,
            entity_type="person",
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
            project_ids=[project_id],
        )
        session.commit()

        assert result.rewired_count == 2
        assert result.deduped_count == 0
        assert result.dropped_self_count == 0

        rows = session.exec(select(StylebookConnection)).all()
        assert len(rows) == 2
        by_nature = {row.nature: row for row in rows}
        assert by_nature["works_for"].from_entity_id == str(target.id)
        assert by_nature["works_for"].to_entity_id == str(org.id)
        assert by_nature["employs"].from_entity_id == str(org.id)
        assert by_nature["employs"].to_entity_id == str(target.id)


def test_rewire_connections_dedupes_when_target_edge_exists() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _org_id, stylebook_id, project_id = _seed(session)
        source = StylebookPersonCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="Jane Source",
            slug="jane-source",
        )
        target = StylebookPersonCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="Jane Target",
            slug="jane-target",
        )
        org = StylebookOrganizationCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="City Council",
            slug="city-council",
            organization_type="government",
        )
        session.add(source)
        session.add(target)
        session.add(org)
        session.commit()

        session.add(
            StylebookConnection(
                project_id=project_id,
                from_entity_type="person",
                from_entity_id=str(source.id),
                to_entity_type="organization",
                to_entity_id=str(org.id),
                nature="works_for",
            )
        )
        session.add(
            StylebookConnection(
                project_id=project_id,
                from_entity_type="person",
                from_entity_id=str(target.id),
                to_entity_type="organization",
                to_entity_id=str(org.id),
                nature="works_for",
            )
        )
        session.commit()

        result = rewire_connections_for_canonical_merge(
            session,
            entity_type="person",
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
            project_ids=[project_id],
        )
        session.commit()

        assert result.rewired_count == 0
        assert result.deduped_count == 1
        rows = session.exec(select(StylebookConnection)).all()
        assert len(rows) == 1
        assert rows[0].from_entity_id == str(target.id)


def test_rewire_connections_drops_self_loop_created_by_merge() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _org_id, stylebook_id, project_id = _seed(session)
        source = StylebookPersonCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="Jane Source",
            slug="jane-source",
        )
        target = StylebookPersonCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="Jane Target",
            slug="jane-target",
        )
        session.add(source)
        session.add(target)
        session.commit()

        session.add(
            StylebookConnection(
                project_id=project_id,
                from_entity_type="person",
                from_entity_id=str(source.id),
                to_entity_type="person",
                to_entity_id=str(target.id),
                nature="related_to",
            )
        )
        session.commit()

        result = rewire_connections_for_canonical_merge(
            session,
            entity_type="person",
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
            project_ids=[project_id],
        )
        session.commit()

        assert result.dropped_self_count == 1
        assert session.exec(select(StylebookConnection)).all() == []


def test_merge_person_canonical_into_rewires_connections() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org_id, stylebook_id, project_id = _seed(session)
        source = StylebookPersonCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="Jane Source",
            slug="jane-source",
        )
        target = StylebookPersonCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="Jane Target",
            slug="jane-target",
        )
        org = StylebookOrganizationCanonical(
            id=str(uuid4()),
            stylebook_id=stylebook_id,
            label="City Council",
            slug="city-council",
            organization_type="government",
        )
        session.add(source)
        session.add(target)
        session.add(org)
        session.commit()

        person = SubstratePerson(
            project_id=project_id,
            name="Jane Source",
            normalized_name="jane source",
            stylebook_person_canonical_id=str(source.id),
            canonical_link_status=CANONICAL_LINK_LINKED,
        )
        session.add(person)
        session.add(
            StylebookConnection(
                project_id=project_id,
                from_entity_type="person",
                from_entity_id=str(source.id),
                to_entity_type="organization",
                to_entity_id=str(org.id),
                nature="works_for",
            )
        )
        session.commit()

        merge_person_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=org_id,
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
        )
        session.commit()

        assert session.get(StylebookPersonCanonical, str(source.id)) is None
        rows = session.exec(select(StylebookConnection)).all()
        assert len(rows) == 1
        assert rows[0].from_entity_id == str(target.id)
        assert rows[0].to_entity_id == str(org.id)
