"""Unit tests for cleanup quality finders."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.quality.finders.duplicate_locations import (
    duplicate_location_cluster_ids,
    duplicate_location_pair_edges,
)
from backfield_entities.quality.finders.duplicate_organizations import (
    duplicate_organization_cluster_ids,
)
from backfield_entities.quality.finders.duplicate_people import duplicate_person_cluster_ids
from backfield_entities.quality.finders.location_geography_issues import (
    count_location_geography_issues,
    list_location_geography_issues,
    substrate_is_distant_from_canonical,
)
from sqlmodel import Session, SQLModel, create_engine


def _make_stylebook(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Test Org", slug="test-org")
    session.add(org)
    session.commit()
    session.refresh(org)
    sb = Stylebook(
        organization_id=int(org.id),
        slug="test-sb",
        name="Test",
        is_default=True,
    )
    session.add(sb)
    session.commit()
    session.refresh(sb)
    assert sb.id is not None
    assert org.id is not None
    return int(sb.id), int(org.id)


def _add_canonical(
    session: Session,
    *,
    stylebook_id: int,
    slug: str,
    label: str,
    geometry_json: dict | None = None,
) -> StylebookLocationCanonical:
    row = StylebookLocationCanonical(
        stylebook_id=stylebook_id,
        slug=slug,
        label=label,
        geometry_json=geometry_json,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_exact_duplicate_location_clustering_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        shared_label = "Ward 36, Chicago, IL"
        _add_canonical(session, stylebook_id=stylebook_id, slug="ward-36-a", label=shared_label)
        _add_canonical(session, stylebook_id=stylebook_id, slug="ward-36-b", label=shared_label)
        session.commit()

        clusters = duplicate_location_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2


def test_fuzzy_duplicate_location_clustering_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="billy-goat-chicago",
            label="Billy Goat Tavern, Chicago, IL",
        )
        _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="billy-goat-west-loop",
            label="Billy Goat Tavern, West Loop, Chicago, IL",
        )
        session.commit()

        clusters = duplicate_location_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2


def test_suffix_only_labels_not_clustered_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="ward-36",
            label="Ward 36, Chicago, IL",
        )
        _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="near-west-side",
            label="Near West Side, Chicago, IL",
        )
        _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="washington-park",
            label="Washington Park, South Side, Chicago, IL",
        )
        session.commit()

        pairs = duplicate_location_pair_edges(session, stylebook_id=stylebook_id)
        assert pairs == []


def test_location_geography_issues_missing_geometry_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, org_id = _make_stylebook(session)
        _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="no-geom",
            label="Place without map",
        )
        _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="with-geom",
            label="Place with map",
            geometry_json={"type": "Point", "coordinates": [-87.6, 41.8]},
        )
        session.commit()

        assert (
            count_location_geography_issues(
                session,
                stylebook_id=stylebook_id,
                organization_id=org_id,
            )
            == 1
        )
        rows, total = list_location_geography_issues(
            session,
            stylebook_id=stylebook_id,
            organization_id=org_id,
            limit=10,
            offset=0,
        )
        assert total == 1
        assert len(rows) == 1
        assert rows[0].label == "Place without map"
        assert rows[0].issue == "missing_geometry"


def test_substrate_is_distant_from_canonical() -> None:
    illinois = {"type": "Point", "coordinates": [-88.28, 42.04]}
    texas = {"type": "Point", "coordinates": [-97.45, 31.05]}
    assert substrate_is_distant_from_canonical(
        substrate_geometry_json=texas,
        canonical_geometry_json=illinois,
    )
    assert not substrate_is_distant_from_canonical(
        substrate_geometry_json=illinois,
        canonical_geometry_json=illinois,
    )


def test_location_geography_issues_distant_linked_places_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, org_id = _make_stylebook(session)
        org = session.get(BackfieldOrganization, org_id)
        assert org is not None
        project = BackfieldProject(organization_id=org_id, name="Demo", slug="demo")
        session.add(project)
        session.commit()
        session.refresh(project)

        canon = _add_canonical(
            session,
            stylebook_id=stylebook_id,
            slug="elgin-il",
            label="Community Center Christian Ministries, Elgin, IL",
            geometry_json={"type": "Point", "coordinates": [-88.28, 42.04]},
        )
        session.add(
            SubstrateLocation(
                project_id=int(project.id),
                name="Community Center Christian Ministries, Elgin, IL",
                normalized_name="community-center-elgin",
                location_type="place",
                identity_fingerprint="fp-distant-tx",
                stylebook_location_canonical_id=str(canon.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
                geometry_json={"type": "Point", "coordinates": [-97.45, 31.05]},
            )
        )
        session.commit()

        rows, total = list_location_geography_issues(
            session,
            stylebook_id=stylebook_id,
            organization_id=org_id,
            limit=10,
            offset=0,
        )
        assert total == 1
        assert rows[0].issue == "distant_linked_places"
        assert rows[0].distant_linked_count == 1


def test_exact_duplicate_person_clustering_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        from backfield_db import StylebookPersonCanonical

        session.add(
            StylebookPersonCanonical(
                stylebook_id=stylebook_id,
                slug="jane-a",
                label="Jane Doe",
            )
        )
        session.add(
            StylebookPersonCanonical(
                stylebook_id=stylebook_id,
                slug="jane-b",
                label="Jane Doe",
            )
        )
        session.commit()

        clusters = duplicate_person_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2


def test_fuzzy_duplicate_person_clustering_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        from backfield_db import StylebookPersonCanonical

        session.add(
            StylebookPersonCanonical(
                stylebook_id=stylebook_id,
                slug="jane-doe",
                label="Jane Doe",
            )
        )
        session.add(
            StylebookPersonCanonical(
                stylebook_id=stylebook_id,
                slug="jane-m-doe",
                label="Jane M. Doe",
            )
        )
        session.commit()

        clusters = duplicate_person_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2


def test_exact_duplicate_organization_clustering_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, _org_id = _make_stylebook(session)
        from backfield_db import StylebookOrganizationCanonical

        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=stylebook_id,
                slug="city-hall-a",
                label="City Hall",
            )
        )
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=stylebook_id,
                slug="city-hall-b",
                label="City Hall",
            )
        )
        session.commit()

        clusters = duplicate_organization_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2
