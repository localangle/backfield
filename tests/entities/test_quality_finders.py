"""Unit tests for cleanup quality finders."""

from __future__ import annotations

from backfield_db import BackfieldOrganization, Stylebook, StylebookLocationCanonical
from backfield_entities.quality.finders.duplicate_locations import (
    count_duplicate_location_clusters,
    duplicate_location_cluster_ids,
)
from backfield_entities.quality.finders.missing_geometry_locations import (
    count_missing_geometry_locations,
    list_missing_geometry_locations,
)
from sqlmodel import Session, SQLModel, create_engine


def _make_stylebook(session: Session) -> int:
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
    return int(sb.id)


def test_duplicate_location_clustering_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id = _make_stylebook(session)
        session.add(
            StylebookLocationCanonical(
                stylebook_id=stylebook_id,
                slug="billy-goat-chicago",
                label="Billy Goat Tavern, Chicago, IL",
            )
        )
        session.add(
            StylebookLocationCanonical(
                stylebook_id=stylebook_id,
                slug="billy-goat-west-loop",
                label="Billy Goat Tavern, West Loop, Chicago, IL",
            )
        )
        session.add(
            StylebookLocationCanonical(
                stylebook_id=stylebook_id,
                slug="unrelated-place",
                label="City Hall, Springfield, IL",
            )
        )
        session.commit()

        clusters = duplicate_location_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2
        assert count_duplicate_location_clusters(session, stylebook_id=stylebook_id) == 1


def test_missing_geometry_locations_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id = _make_stylebook(session)
        session.add(
            StylebookLocationCanonical(
                stylebook_id=stylebook_id,
                slug="no-geom",
                label="Place without map",
            )
        )
        session.add(
            StylebookLocationCanonical(
                stylebook_id=stylebook_id,
                slug="with-geom",
                label="Place with map",
                geometry_json={"type": "Point", "coordinates": [-87.6, 41.8]},
            )
        )
        session.commit()

        assert count_missing_geometry_locations(session, stylebook_id=stylebook_id) == 1
        rows, total = list_missing_geometry_locations(
            session,
            stylebook_id=stylebook_id,
            limit=10,
            offset=0,
        )
        assert total == 1
        assert len(rows) == 1
        assert rows[0].label == "Place without map"
