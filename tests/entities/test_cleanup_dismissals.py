"""Tests for stylebook cleanup dismissal persistence and filtering."""

from __future__ import annotations

import pytest
from backfield_db import (
    BackfieldOrganization,
    Stylebook,
    StylebookLocationCanonical,
    StylebookPersonCanonical,
)
from backfield_entities.quality.dismissals import (
    dismiss_canonical_issue,
    dismiss_cluster_members,
    pair_key_for_ids,
)
from backfield_entities.quality.finders.duplicate_locations import (
    count_duplicate_location_clusters,
    duplicate_location_cluster_ids,
)
from backfield_entities.quality.finders.duplicate_people import (
    count_duplicate_person_clusters,
)
from backfield_entities.quality.finders.location_geography_issues import (
    count_location_geography_issues,
)
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture
def dismissal_engine(tmp_path) -> Engine:
    database_path = tmp_path / "cleanup-dismissals.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Backfield", slug="default")
        session.add(org)
        session.commit()
        session.refresh(org)
        sb = Stylebook(
            organization_id=int(org.id),
            slug="default",
            name="Default",
            is_default=True,
        )
        session.add(sb)
        session.commit()
        session.refresh(sb)
        sb_id = int(sb.id)
        session.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="loc-a",
                label="Ward 36, Chicago, IL",
            )
        )
        session.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="loc-b",
                label="Ward 36, Chicago, IL",
            )
        )
        session.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="loc-c",
                label="Near West Side, Chicago, IL",
            )
        )
        session.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="missing-geom",
                label="No map pin",
            )
        )
        session.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                slug="person-a",
                label="Jane Doe",
            )
        )
        session.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                slug="person-b",
                label="Jane Doe",
            )
        )
        session.commit()
    return engine


def test_pair_key_is_order_independent() -> None:
    assert pair_key_for_ids("b", "a") == pair_key_for_ids("a", "b")


def test_dismiss_cluster_pair_hides_exact_duplicate_cluster(dismissal_engine: Engine) -> None:
    with Session(dismissal_engine) as session:
        sb = session.exec(select(Stylebook)).one()
        stylebook_id = int(sb.id)
        locs = session.exec(
            select(StylebookLocationCanonical).where(
                StylebookLocationCanonical.stylebook_id == stylebook_id,
                StylebookLocationCanonical.slug.in_(["loc-a", "loc-b"]),
            )
        ).all()
        member_ids = sorted(str(row.id) for row in locs if row.id is not None)
        assert len(member_ids) == 2
        assert count_duplicate_location_clusters(session, stylebook_id=stylebook_id) == 1
        dismiss_cluster_members(
            session,
            stylebook_id=stylebook_id,
            check_id="duplicate-locations",
            member_ids=member_ids,
        )
        session.commit()
        assert count_duplicate_location_clusters(session, stylebook_id=stylebook_id) == 0


def test_dismissed_pair_resurfaces_only_via_new_duplicate_edges(dismissal_engine: Engine) -> None:
    with Session(dismissal_engine) as session:
        sb = session.exec(select(Stylebook)).one()
        stylebook_id = int(sb.id)
        by_slug = {
            row.slug: str(row.id)
            for row in session.exec(
                select(StylebookLocationCanonical).where(
                    StylebookLocationCanonical.stylebook_id == stylebook_id
                )
            ).all()
            if row.id is not None
        }
        dismiss_cluster_members(
            session,
            stylebook_id=stylebook_id,
            check_id="duplicate-locations",
            member_ids=[by_slug["loc-a"], by_slug["loc-b"]],
        )
        session.commit()
        assert count_duplicate_location_clusters(session, stylebook_id=stylebook_id) == 0
        session.add(
            StylebookLocationCanonical(
                stylebook_id=stylebook_id,
                slug="loc-d",
                label="Ward 36, Chicago, IL",
            )
        )
        session.commit()
        loc_d_id = str(
            session.exec(
                select(StylebookLocationCanonical).where(StylebookLocationCanonical.slug == "loc-d")
            ).one().id
        )
        clusters = duplicate_location_cluster_ids(session, stylebook_id=stylebook_id)
        assert len(clusters) == 1
        assert loc_d_id in clusters[0]
        assert count_duplicate_location_clusters(session, stylebook_id=stylebook_id) == 1


def test_dismiss_canonical_hides_geography_issue(dismissal_engine: Engine) -> None:
    with Session(dismissal_engine) as session:
        sb = session.exec(select(Stylebook)).one()
        stylebook_id = int(sb.id)
        org_id = int(sb.organization_id)
        missing = session.exec(
            select(StylebookLocationCanonical).where(
                StylebookLocationCanonical.slug == "missing-geom"
            )
        ).one()
        before = count_location_geography_issues(
            session,
            stylebook_id=stylebook_id,
            organization_id=org_id,
        )
        assert before >= 1
        dismiss_canonical_issue(
            session,
            stylebook_id=stylebook_id,
            check_id="missing-geometry-locations",
            canonical_id=str(missing.id),
        )
        session.commit()
        after = count_location_geography_issues(
            session,
            stylebook_id=stylebook_id,
            organization_id=org_id,
        )
        assert after == before - 1


def test_dismiss_person_cluster(dismissal_engine: Engine) -> None:
    with Session(dismissal_engine) as session:
        sb = session.exec(select(Stylebook)).one()
        stylebook_id = int(sb.id)
        people = session.exec(
            select(StylebookPersonCanonical).where(
                StylebookPersonCanonical.stylebook_id == stylebook_id
            )
        ).all()
        member_ids = sorted(str(row.id) for row in people if row.id is not None)
        assert count_duplicate_person_clusters(session, stylebook_id=stylebook_id) == 1
        dismiss_cluster_members(
            session,
            stylebook_id=stylebook_id,
            check_id="duplicate-people",
            member_ids=member_ids,
        )
        session.commit()
        assert count_duplicate_person_clusters(session, stylebook_id=stylebook_id) == 0
