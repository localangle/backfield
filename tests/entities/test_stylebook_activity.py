from __future__ import annotations

from backfield_db import BackfieldOrganization, Stylebook, StylebookActivity
from backfield_entities.activity import (
    EVENT_CANONICAL_CREATED,
    log_stylebook_activity,
    log_stylebook_activity_safe,
)
from sqlmodel import Session, SQLModel, create_engine, select


def _seed_stylebook(session: Session) -> int:
    org = BackfieldOrganization(name="Backfield", slug="default")
    session.add(org)
    session.commit()
    session.refresh(org)
    stylebook = Stylebook(
        organization_id=int(org.id),
        slug="default",
        name="Default Stylebook",
        is_default=True,
    )
    session.add(stylebook)
    session.commit()
    session.refresh(stylebook)
    return int(stylebook.id)


def test_log_stylebook_activity_writes_event_row(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'activity.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id = _seed_stylebook(session)
        log_stylebook_activity(
            session,
            stylebook_id=stylebook_id,
            source="manual_ui",
            event_type=EVENT_CANONICAL_CREATED,
            actor_type="user",
            entity_type="person",
            entity_id="person-1",
            entity_label="Jane Doe",
        )
        session.commit()
        rows = session.exec(select(StylebookActivity)).all()
        assert len(rows) == 1
        assert rows[0].event_type == EVENT_CANONICAL_CREATED
        assert rows[0].entity_id == "person-1"


def test_log_stylebook_activity_safe_swallow_errors(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'activity-safe.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # Missing stylebook id should not raise.
        log_stylebook_activity_safe(
            session,
            stylebook_id=999999,
            source="manual_ui",
            event_type="test_event",
        )
