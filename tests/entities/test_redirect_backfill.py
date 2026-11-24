"""Backfilling merged_into redirects from the activity log."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    Stylebook,
    StylebookCanonicalRedirect,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
)
from backfield_entities.activity import EVENT_CLEANUP_MERGE, log_stylebook_activity
from backfield_entities.cleanup.redirect_backfill import backfill_merge_redirects
from backfield_entities.cleanup.redirects import record_redirect, resolve_canonical
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select


def _engine(tmp_path) -> Engine:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'redirect-backfill.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _stylebook(session: Session, slug: str) -> int:
    org = BackfieldOrganization(name=slug, slug=slug)
    session.add(org)
    session.commit()
    stylebook = Stylebook(organization_id=int(org.id), slug=slug, name=slug, is_default=True)
    session.add(stylebook)
    session.commit()
    return int(stylebook.id)


def _live_places(session: Session, stylebook_id: int, *ids: str) -> None:
    for place_id in ids:
        session.add(
            StylebookLocationCanonical(
                id=place_id, stylebook_id=stylebook_id, label=place_id, slug=place_id
            )
        )
    session.commit()


def _merge_event(
    session: Session,
    stylebook_id: int,
    old_id: str,
    new_id: str,
    *,
    entity_type: str = "location",
) -> None:
    log_stylebook_activity(
        session,
        stylebook_id=stylebook_id,
        source="cleanup_check",
        event_type=EVENT_CLEANUP_MERGE,
        entity_type=entity_type,
        entity_id=old_id,
        related_entity_type=entity_type,
        related_entity_id=new_id,
    )
    session.commit()


def _redirects(session: Session) -> dict[str, str]:
    session.expire_all()
    return {r.old_id: r.new_id for r in session.exec(select(StylebookCanonicalRedirect)).all()}


def test_backfill_writes_safe_redirects_and_skips_the_rest(tmp_path) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as session:
        sb = _stylebook(session, "one")
        _live_places(session, sb, "survivor", "end", "still-here", "kept")
        _merge_event(session, sb, "gone", "survivor")
        _merge_event(session, sb, "hop-1", "hop-2")
        _merge_event(session, sb, "hop-2", "end")
        _merge_event(session, sb, "lost", "deleted-survivor")
        _merge_event(session, sb, "still-here", "survivor")
        _merge_event(session, sb, "cycle-a", "cycle-b")
        _merge_event(session, sb, "cycle-b", "cycle-a")
        _merge_event(session, sb, "has-redirect", "survivor")
        record_redirect(
            session, stylebook_id=sb, entity_type="location", old_id="has-redirect", new_id="kept"
        )
        session.commit()
        # Events that are not merges of a record are ignored.
        _merge_event(session, sb, "check-1", "proposal-1", entity_type="check")

        dry = backfill_merge_redirects(session, dry_run=True)
        assert _redirects(session) == {"has-redirect": "kept"}
        report = backfill_merge_redirects(session, dry_run=False)
        session.commit()
        again = backfill_merge_redirects(session, dry_run=False)

    counts = report.by_entity["location"]
    assert (dry.counts.written, report.counts.written) == (3, 3)
    assert counts.merges_found == 8
    assert counts.already_present == 1
    assert counts.old_record_still_exists == 1
    assert counts.survivor_missing == 1
    assert counts.cycles == 2
    assert report.survivor_missing_samples == ["lost"]
    with Session(engine) as session:
        assert _redirects(session) == {
            "gone": "survivor",
            "hop-1": "end",
            "hop-2": "end",
            "has-redirect": "kept",
        }
        resolved = resolve_canonical(
            session, stylebook_id=sb, entity_type="location", canonical_id="hop-1"
        )
        assert (resolved.resolved_id, resolved.merged) == ("end", True)
    assert again.counts.written == 0
    assert again.counts.already_present == 4


def test_agent_maintenance_events_list_their_sources_in_the_payload(tmp_path) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as session:
        sb = _stylebook(session, "one")
        session.add(
            StylebookOrganizationCanonical(
                id="org-target", stylebook_id=sb, label="Acme", slug="acme"
            )
        )
        session.commit()
        for mode, sources in (("apply", ["org-a", "org-b"]), ("dry_run", ["org-dry"])):
            log_stylebook_activity(
                session,
                stylebook_id=sb,
                source="stylebook_agent_maintenance",
                event_type=EVENT_CLEANUP_MERGE,
                entity_type="organization",
                entity_id="org-target",
                payload_json={"target_id": "org-target", "source_ids": sources, "mode": mode},
            )
        session.commit()

        backfill_merge_redirects(session, dry_run=False)
        session.commit()
        assert _redirects(session) == {"org-a": "org-target", "org-b": "org-target"}


def test_backfill_keeps_stylebooks_apart_and_can_be_limited(tmp_path) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as session:
        first = _stylebook(session, "one")
        second = _stylebook(session, "two")
        _live_places(session, first, "survivor-one")
        _live_places(session, second, "survivor-two")
        _merge_event(session, first, "gone-one", "survivor-one")
        # The survivor named here lives in the other Stylebook, so it does not count as live here.
        _merge_event(session, second, "gone-two", "survivor-one")
        _merge_event(session, second, "gone-three", "survivor-two")

        backfill_merge_redirects(session, stylebook_id=second, dry_run=False)
        session.commit()
        only_second = _redirects(session)
        backfill_merge_redirects(session, dry_run=False)
        session.commit()

        assert only_second == {"gone-three": "survivor-two"}
        assert _redirects(session) == {
            "gone-one": "survivor-one",
            "gone-three": "survivor-two",
        }
