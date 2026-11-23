"""The shared merge apply function: merge, activity row, and reindex callback."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from backfield_db import (
    StylebookActivity,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateLocation,
    SubstrateOrganization,
    SubstratePerson,
)
from backfield_entities.activity import EVENT_CLEANUP_MERGE
from backfield_entities.cleanup.apply_merge import MergeActivity, MergeRequest, apply_merge
from sqlmodel import Session, select

from tests.entities.test_merge_cleanup_semantics import _location, _seed, _session


class _RecordingReindex:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, int]] = []

    def __call__(
        self, session: Session, *, project_id: int, entity_type: str, entity_id: int
    ) -> None:
        self.calls.append((project_id, entity_type, entity_id))


def _linked_location_pair(
    session: Session, stylebook_id: int, project_id: int
) -> tuple[StylebookLocationCanonical, StylebookLocationCanonical, SubstrateLocation]:
    source = _location(session, stylebook_id=stylebook_id, label="Wrigley Fld, Chicago, IL")
    target = _location(session, stylebook_id=stylebook_id, label="Wrigley Field, Chicago, IL")
    substrate = SubstrateLocation(
        project_id=project_id,
        name="Wrigley Fld, Chicago, IL",
        normalized_name="wrigley fld, chicago, il",
        location_type="place",
        stylebook_location_canonical_id=str(source.id),
        canonical_link_status="linked",
    )
    session.add(substrate)
    session.commit()
    return source, target, substrate


def test_apply_merge_runs_merge_reindexes_and_logs_activity() -> None:
    with _session() as session:
        organization_id, stylebook_id, project_id = _seed(session)
        source, target, substrate = _linked_location_pair(session, stylebook_id, project_id)
        reindex = _RecordingReindex()

        outcome = apply_merge(
            session,
            MergeRequest(
                entity_type="location",
                stylebook_id=stylebook_id,
                organization_id=organization_id,
                source_canonical_id=str(source.id),
                target_canonical_id=str(target.id),
            ),
            reindex=reindex,
            activity=MergeActivity(
                actor_type="agent",
                source="cleanup_ai",
                payload={"run_id": "run-1", "provenance": "stylebook_cleanup_merge"},
            ),
        )
        session.commit()

        assert outcome.source_label == "Wrigley Fld, Chicago, IL"
        assert outcome.target_label == "Wrigley Field, Chicago, IL"
        assert outcome.relinked_substrate_count == 1
        assert reindex.calls == [(project_id, "location", int(substrate.id))]  # type: ignore[arg-type]
        assert session.get(StylebookLocationCanonical, str(source.id)) is None

        row = session.exec(select(StylebookActivity)).one()
        assert row.event_type == EVENT_CLEANUP_MERGE
        assert (row.actor_type, row.source) == ("agent", "cleanup_ai")
        assert (row.entity_id, row.related_entity_id) == (str(source.id), str(target.id))
        assert row.entity_label == "Wrigley Fld, Chicago, IL"
        assert row.payload_json == {"run_id": "run-1", "provenance": "stylebook_cleanup_merge"}


def test_apply_merge_without_activity_or_reindex_only_merges() -> None:
    with _session() as session:
        organization_id, stylebook_id, project_id = _seed(session)
        source, target, _substrate = _linked_location_pair(session, stylebook_id, project_id)

        apply_merge(
            session,
            MergeRequest(
                entity_type="location",
                stylebook_id=stylebook_id,
                organization_id=organization_id,
                source_canonical_id=str(source.id),
                target_canonical_id=str(target.id),
            ),
            reindex=None,
        )
        session.commit()

        assert session.exec(select(StylebookActivity)).all() == []


def test_apply_merge_surfaces_guard_refusals_without_side_effects() -> None:
    with _session() as session:
        organization_id, stylebook_id, _project_id = _seed(session)
        city = _location(
            session, stylebook_id=stylebook_id, label="Chicago, IL", location_type="city"
        )
        venue = _location(session, stylebook_id=stylebook_id, label="Perman, Chicago, IL")
        session.commit()
        reindex = _RecordingReindex()

        with pytest.raises(ValueError, match="different kinds of places"):
            apply_merge(
                session,
                MergeRequest(
                    entity_type="location",
                    stylebook_id=stylebook_id,
                    organization_id=organization_id,
                    source_canonical_id=str(venue.id),
                    target_canonical_id=str(city.id),
                ),
                reindex=reindex,
                activity=MergeActivity(actor_type="user"),
            )
        assert reindex.calls == []
        assert session.exec(select(StylebookActivity)).all() == []


@pytest.mark.parametrize("entity_type", ["person", "organization"])
def test_apply_merge_handles_people_and_organizations(entity_type: str) -> None:
    models: dict[str, Any] = {
        "person": (StylebookPersonCanonical, SubstratePerson, "stylebook_person_canonical_id"),
        "organization": (
            StylebookOrganizationCanonical,
            SubstrateOrganization,
            "stylebook_organization_canonical_id",
        ),
    }
    canonical_model, substrate_model, link_column = models[entity_type]
    with _session() as session:
        organization_id, stylebook_id, project_id = _seed(session)
        source = canonical_model(
            stylebook_id=stylebook_id, label="Source Name", slug=f"source-{uuid4().hex[:6]}"
        )
        target = canonical_model(
            stylebook_id=stylebook_id, label="Target Name", slug=f"target-{uuid4().hex[:6]}"
        )
        session.add_all([source, target])
        session.flush()
        substrate = substrate_model(
            project_id=project_id,
            name="Source Name",
            normalized_name="source name",
            canonical_link_status="linked",
            **{link_column: str(source.id)},
        )
        session.add(substrate)
        session.commit()
        reindex = _RecordingReindex()

        outcome = apply_merge(
            session,
            MergeRequest(
                entity_type=entity_type,  # type: ignore[arg-type]
                stylebook_id=stylebook_id,
                organization_id=organization_id,
                source_canonical_id=str(source.id),
                target_canonical_id=str(target.id),
            ),
            reindex=reindex,
            activity=MergeActivity(actor_type="user", actor_user_id=None),
        )
        session.commit()

        assert outcome.entity_type == entity_type
        assert outcome.source_deleted is True
        assert reindex.calls == [(project_id, entity_type, int(substrate.id))]
        assert session.exec(select(StylebookActivity)).one().entity_type == entity_type
