"""Tests for concurrent Stylebook canonical slug allocation retries."""

from __future__ import annotations

from unittest.mock import patch

from backfield_db import (
    BackfieldOrganization,
    Stylebook,
    StylebookPersonCanonical,
    SubstratePerson,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.entities.person import materialize_new_canonical_and_link
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_stylebook(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-slug-retry")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = Stylebook(organization_id=oid, slug="default", name="Default", is_default=True)
    session.add(sb)
    session.commit()
    session.refresh(sb)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    return sb_id, oid


def test_materialize_person_canonical_retries_when_slug_raced() -> None:
    """Concurrent ingest can claim a slug between allocate and insert."""
    engine = _engine()
    with Session(engine) as session:
        sb_id, _oid = _seed_stylebook(session)
        session.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                label="Emanuel Welch",
                slug="emanuel-welch",
                affiliation="Illinois House of Representatives",
                status="active",
            )
        )
        session.commit()

        person = SubstratePerson(
            project_id=1,
            name="Emanuel Welch",
            normalized_name="emanuel welch",
            title="House Speaker",
            affiliation="Illinois House of Representatives",
            public_figure=True,
            person_type="elected_official",
            sort_key="welch",
            canonical_link_status="pending",
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        calls = {"n": 0}

        def _stale_then_fresh(sess: Session, *, stylebook_id: int, label: str) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return "emanuel-welch"
            return "emanuel-welch-2"

        with patch(
            "backfield_entities.entities.person.persist.allocate_unique_person_canonical_slug",
            side_effect=_stale_then_fresh,
        ):
            materialize_new_canonical_and_link(session, stylebook_id=sb_id, person=person)
        session.commit()
        session.refresh(person)

        assert person.canonical_link_status == CANONICAL_LINK_LINKED
        canon = session.get(StylebookPersonCanonical, str(person.stylebook_person_canonical_id))
        assert canon is not None
        assert canon.slug == "emanuel-welch-2"
