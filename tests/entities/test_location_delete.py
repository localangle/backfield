"""Tests for delete_location_canonical_and_requeue."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_entities.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
)
from backfield_entities.entities.location.delete import (
    delete_location_canonical_and_requeue,
)
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine


def _engine(tmp_path) -> Engine:
    path = tmp_path / "delete-canonical.db"
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_delete_location_canonical_and_requeue(tmp_path) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org")
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
        project = BackfieldProject(
            organization_id=int(org.id),
            name="Demo",
            slug="demo",
        )
        session.add(project)
        session.commit()
        session.refresh(project)

        canon = StylebookLocationCanonical(
            stylebook_id=int(sb.id),
            slug="will-smith-tx",
            label="Will Smith, TX",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)

        loc = SubstrateLocation(
            project_id=int(project.id),
            name="Will Smith, TX",
            normalized_name="will smith tx",
            location_type="place",
            stylebook_location_canonical_id=str(canon.id),
            canonical_link_status=CANONICAL_LINK_LINKED,
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)
        sid = int(loc.id)
        cid = str(canon.id)

        result = delete_location_canonical_and_requeue(
            session,
            stylebook_id=int(sb.id),
            organization_id=int(org.id),
            canonical_id=cid,
            source="manual_ui",
        )
        session.commit()

        assert result.canonical_id == cid
        assert result.unlinked_substrate_count == 1
        assert result.unlinked_substrate_ids == [sid]
        assert session.get(StylebookLocationCanonical, cid) is None
        refreshed = session.get(SubstrateLocation, sid)
        assert refreshed is not None
        assert refreshed.stylebook_location_canonical_id is None
        assert refreshed.canonical_link_status == CANONICAL_LINK_PENDING
        reasons = refreshed.canonical_review_reasons_json or []
        assert reasons[0]["code"] == "reset_pending_after_canonical_deleted"


def test_delete_stale_substrate_guard(tmp_path) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org2")
        session.add(org)
        session.commit()
        session.refresh(org)
        sb = Stylebook(
            organization_id=int(org.id),
            slug="sb2",
            name="SB2",
            is_default=True,
        )
        session.add(sb)
        session.commit()
        session.refresh(sb)
        project = BackfieldProject(
            organization_id=int(org.id), name="P", slug="p"
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        canon = StylebookLocationCanonical(
            stylebook_id=int(sb.id),
            slug="x",
            label="X",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        try:
            delete_location_canonical_and_requeue(
                session,
                stylebook_id=int(sb.id),
                organization_id=int(org.id),
                canonical_id=str(canon.id),
                expected_substrate_ids=[999],
            )
            raise AssertionError("expected stale_preview")
        except ValueError as exc:
            assert "stale_preview" in str(exc)
