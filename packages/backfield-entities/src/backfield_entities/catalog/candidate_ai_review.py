"""Open candidate queue scope for background AI review runs."""

from __future__ import annotations

from typing import Literal

from backfield_db import SubstrateLocation, SubstrateOrganization, SubstratePerson
from sqlalchemy import func
from sqlmodel import Session, col, select

from backfield_entities.canonical.link import CANONICAL_LINK_PENDING

CandidateAiReviewEntityType = Literal["person", "organization", "location"]


def _open_person_candidate_ids(session: Session, *, project_id: int) -> list[int]:
    sort_key = func.coalesce(col(SubstratePerson.sort_key), col(SubstratePerson.normalized_name))
    rows = session.exec(
        select(SubstratePerson.id)
        .where(
            SubstratePerson.project_id == project_id,
            col(SubstratePerson.stylebook_person_canonical_id).is_(None),
            SubstratePerson.canonical_link_status == CANONICAL_LINK_PENDING,
        )
        .order_by(sort_key)
    ).all()
    return [int(row) for row in rows if row is not None]


def _open_organization_candidate_ids(session: Session, *, project_id: int) -> list[int]:
    rows = session.exec(
        select(SubstrateOrganization.id)
        .where(
            SubstrateOrganization.project_id == project_id,
            col(SubstrateOrganization.stylebook_organization_canonical_id).is_(None),
            SubstrateOrganization.canonical_link_status == CANONICAL_LINK_PENDING,
        )
        .order_by(col(SubstrateOrganization.normalized_name))
    ).all()
    return [int(row) for row in rows if row is not None]


def _open_location_candidate_ids(session: Session, *, project_id: int) -> list[int]:
    rows = session.exec(
        select(SubstrateLocation.id)
        .where(
            SubstrateLocation.project_id == project_id,
            col(SubstrateLocation.stylebook_location_canonical_id).is_(None),
            SubstrateLocation.canonical_link_status == CANONICAL_LINK_PENDING,
        )
        .order_by(col(SubstrateLocation.normalized_name))
    ).all()
    return [int(row) for row in rows if row is not None]


def list_open_candidate_ids_for_review(
    session: Session,
    *,
    entity_type: CandidateAiReviewEntityType,
    project_id: int,
) -> list[int]:
    if entity_type == "person":
        return _open_person_candidate_ids(session, project_id=project_id)
    if entity_type == "organization":
        return _open_organization_candidate_ids(session, project_id=project_id)
    if entity_type == "location":
        return _open_location_candidate_ids(session, project_id=project_id)
    raise ValueError(f"Unsupported candidate AI review entity_type: {entity_type}")


def count_open_candidates_for_review(
    session: Session,
    *,
    entity_type: CandidateAiReviewEntityType,
    project_id: int,
) -> int:
    return len(
        list_open_candidate_ids_for_review(
            session,
            entity_type=entity_type,
            project_id=project_id,
        )
    )
