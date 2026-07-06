"""Location canonical recall with accent/apostrophe tolerance."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    Stylebook,
    StylebookLocationCanonical,
)
from backfield_entities.entities.location.persist import seed_aliases_for_canonical_label
from backfield_entities.entities.location.recall import canonical_ids_from_location_name_keys
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_stylebook(session: Session) -> int:
    org = BackfieldOrganization(name="Org", slug="org-location-recall")
    session.add(org)
    session.commit()
    session.refresh(org)
    sb = Stylebook(
        organization_id=int(org.id),  # type: ignore[arg-type]
        slug="default",
        name="Default",
        is_default=True,
    )
    session.add(sb)
    session.commit()
    session.refresh(sb)
    return int(sb.id)  # type: ignore[arg-type]


def test_canonical_ids_from_location_name_keys_unicode_apostrophe() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id = _seed_stylebook(session)
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Cook County State\u2019s Attorney\u2019s Office, IL",
            slug="cook-county-states-attorneys-office-il",
            status="active",
        )
        session.add(canon)
        session.flush()
        assert canon.id is not None
        seed_aliases_for_canonical_label(
            session,
            canon_id=str(canon.id),
            label=str(canon.label),
            provenance="test",
        )
        session.commit()
        cid = str(canon.id)

        hits = canonical_ids_from_location_name_keys(
            session,
            stylebook_id=sb_id,
            name_or_norm="Cook County State's Attorney's Office, IL",
        )
        assert hits == [cid]


def test_canonical_ids_from_location_name_keys_accent_fold() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id = _seed_stylebook(session)
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="São Paulo, Brazil",
            slug="sao-paulo-brazil",
            status="active",
        )
        session.add(canon)
        session.flush()
        assert canon.id is not None
        seed_aliases_for_canonical_label(
            session,
            canon_id=str(canon.id),
            label=str(canon.label),
            provenance="test",
        )
        session.commit()
        cid = str(canon.id)

        hits = canonical_ids_from_location_name_keys(
            session,
            stylebook_id=sb_id,
            name_or_norm="Sao Paulo, Brazil",
        )
        assert hits == [cid]
