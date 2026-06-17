"""Unit tests for cleanup quality finders."""

from __future__ import annotations

from backfield_db import BackfieldOrganization, Stylebook, StylebookLocationCanonical
from backfield_entities.quality.finders.duplicate_locations import (
    duplicate_location_cluster_ids,
    duplicate_location_pair_edges,
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


def _add_canonical(
    session: Session,
    *,
    stylebook_id: int,
    slug: str,
    label: str,
) -> None:
    session.add(
        StylebookLocationCanonical(
            stylebook_id=stylebook_id,
            slug=slug,
            label=label,
        )
    )


def test_exact_duplicate_location_clustering_sqlite() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id = _make_stylebook(session)
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
        stylebook_id = _make_stylebook(session)
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
        stylebook_id = _make_stylebook(session)
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
