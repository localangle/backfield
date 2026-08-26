"""Custom natures catalog helpers for Phase A KG."""

from __future__ import annotations

from backfield_db import Stylebook, StylebookConnectionNatureCustom
from backfield_entities.connections.custom_natures import (
    delete_custom_nature,
    ensure_custom_nature_for_manual_slug,
    merged_nature_catalog,
    upsert_custom_nature,
)
from sqlmodel import Session, SQLModel, create_engine


def _seed_stylebook(session: Session) -> int:
    sb = Stylebook(organization_id=1, slug="kg-test", name="KG Test")
    session.add(sb)
    session.commit()
    session.refresh(sb)
    assert sb.id is not None
    return int(sb.id)


def test_merged_catalog_includes_preferred_and_custom() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id = _seed_stylebook(session)
        upsert_custom_nature(
            session,
            stylebook_id=stylebook_id,
            slug="board_ally",
            label="Board ally",
            equivalent_to="affiliated_with",
        )
        session.commit()
        entries = merged_nature_catalog(session, stylebook_id=stylebook_id)
        by_slug = {e.slug: e for e in entries}
        assert "member_of" in by_slug
        assert by_slug["member_of"].source == "preferred"
        assert by_slug["board_ally"].source == "custom"
        assert by_slug["board_ally"].label == "Board ally"


def test_ensure_custom_nature_for_freeform_slug() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id = _seed_stylebook(session)
        slug = ensure_custom_nature_for_manual_slug(
            session,
            stylebook_id=stylebook_id,
            nature="Neighborhood Liaison",
        )
        session.commit()
        assert slug == "neighborhood_liaison"
        row = session.get(StylebookConnectionNatureCustom, 1)
        assert row is not None
        assert row.slug == "neighborhood_liaison"
        preferred = ensure_custom_nature_for_manual_slug(
            session,
            stylebook_id=stylebook_id,
            nature="member_of",
        )
        assert preferred == "member_of"
        assert delete_custom_nature(
            session, stylebook_id=stylebook_id, slug="neighborhood_liaison"
        )
        session.commit()
