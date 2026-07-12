"""Tests for questionable person cleanup check item construction."""

from __future__ import annotations

import pytest
from backfield_db import (
    BackfieldOrganization,
    Stylebook,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from backfield_entities.quality.check_runs import CleanupRunScope
from backfield_entities.quality.finders.questionable_people import (
    build_questionable_person_check_items,
    prefilter_questionable_person_canonicals,
)
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture
def questionable_person_engine(tmp_path) -> Engine:
    database_path = tmp_path / "questionable-person-check.db"
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
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                slug="wbez-person",
                label="WBEZ",
                person_type="media_journalism",
            )
        )
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=sb_id,
                slug="wbez-org",
                label="WBEZ",
                organization_type="media",
            )
        )
        session.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                slug="cdot-spokesperson",
                label="Chicago Department of Transportation spokesperson",
                person_type="government_official",
            )
        )
        session.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                slug="jane-doe",
                label="Jane Doe",
                person_type="government_official",
            )
        )
        session.commit()
    return engine


def test_prefilter_questionable_person_canonicals_flags_org_like_rows(
    questionable_person_engine: Engine,
) -> None:
    with Session(questionable_person_engine) as session:
        sb = session.exec(select(Stylebook)).one()
        prefiltered = prefilter_questionable_person_canonicals(
            session,
            stylebook_id=int(sb.id),
        )
    by_label = {str(row.label): scored for row, scored in prefiltered}
    assert "WBEZ" in by_label
    assert "cross_catalog_organization" in by_label["WBEZ"].signals
    assert "media_outlet" in by_label["WBEZ"].signals
    assert "Chicago Department of Transportation spokesperson" in by_label
    assert "role_phrase_without_person_name" in by_label[
        "Chicago Department of Transportation spokesperson"
    ].signals
    assert "Jane Doe" not in by_label


def test_build_questionable_person_check_items_payload(
    questionable_person_engine: Engine,
) -> None:
    with Session(questionable_person_engine) as session:
        sb = session.exec(select(Stylebook)).one()
        org = session.exec(select(BackfieldOrganization)).one()
        scope = CleanupRunScope(
            stylebook_id=int(sb.id),
            organization_id=int(org.id),
            check_id="questionable-person-canonicals",
            full_threshold=0.84,
            head_threshold=0.75,
            project_ids=(),
            project_slug=None,
        )
        items = build_questionable_person_check_items(session, scope=scope)
    by_label = {item.label: item for item in items}
    assert by_label["WBEZ"].payload["category"] == "organization_like"
    assert by_label["WBEZ"].payload["matching_organization_type"] == "media"
    assert "cross_catalog_organization" in by_label["WBEZ"].payload["prefilter_signals"]
    assert by_label["Chicago Department of Transportation spokesperson"].payload[
        "suggested_entity_type"
    ] in {"organization", "unknown"}
