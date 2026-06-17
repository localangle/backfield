"""Merge one person canonical into another (relink substrates, delete source)."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db import (
    BackfieldProject,
    StylebookPersonCanonical,
    SubstratePerson,
)
from sqlmodel import Session, col, func, select

from backfield_entities.entities.person.persist import link_substrate_to_canonical_atomic


@dataclass(frozen=True)
class MergePersonCanonicalResult:
    source_id: str
    target_id: str
    relinked_substrate_count: int
    source_deleted: bool
    relinked_substrates: tuple[tuple[int, int], ...]


def _organization_project_ids(session: Session, *, organization_id: int) -> list[int]:
    rows = session.exec(
        select(BackfieldProject.id).where(BackfieldProject.organization_id == organization_id)
    ).all()
    return [int(row) for row in rows if row is not None]


def _linked_substrate_count(
    session: Session,
    *,
    project_ids: list[int],
    canonical_id: str,
) -> int:
    if not project_ids:
        return 0
    return int(
        session.scalar(
            select(func.count())
            .select_from(SubstratePerson)
            .where(
                col(SubstratePerson.project_id).in_(project_ids),
                SubstratePerson.stylebook_person_canonical_id == canonical_id,
            )
        )
        or 0
    )


def merge_person_canonical_into(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    source_canonical_id: str,
    target_canonical_id: str,
    provenance: str = "stylebook_cleanup_merge",
) -> MergePersonCanonicalResult:
    source_id = str(source_canonical_id)
    target_id = str(target_canonical_id)
    if source_id == target_id:
        raise ValueError("source and target canonical must differ")

    source = session.get(StylebookPersonCanonical, source_id)
    target = session.get(StylebookPersonCanonical, target_id)
    if source is None or int(source.stylebook_id) != int(stylebook_id):
        raise ValueError("source canonical not in this stylebook")
    if target is None or int(target.stylebook_id) != int(stylebook_id):
        raise ValueError("target canonical not in this stylebook")

    project_ids = _organization_project_ids(session, organization_id=organization_id)
    linked = list(
        session.exec(
            select(SubstratePerson).where(
                col(SubstratePerson.project_id).in_(project_ids),
                SubstratePerson.stylebook_person_canonical_id == source_id,
            )
        ).all()
    )

    relinked = 0
    relinked_substrates: list[tuple[int, int]] = []
    for person in linked:
        link_substrate_to_canonical_atomic(
            session,
            stylebook_id=int(stylebook_id),
            person=person,
            target_canonical_id=target_id,
            provenance=provenance,
        )
        relinked += 1
        if person.id is not None and person.project_id is not None:
            relinked_substrates.append((int(person.project_id), int(person.id)))

    remaining = _linked_substrate_count(
        session,
        project_ids=project_ids,
        canonical_id=source_id,
    )
    if remaining > 0:
        raise ValueError("source canonical still has linked people after merge")

    session.delete(source)
    return MergePersonCanonicalResult(
        source_id=source_id,
        target_id=target_id,
        relinked_substrate_count=relinked,
        source_deleted=True,
        relinked_substrates=tuple(relinked_substrates),
    )


def canonical_has_linked_evidence(
    session: Session,
    *,
    organization_id: int,
    canonical_id: str,
) -> bool:
    project_ids = _organization_project_ids(session, organization_id=organization_id)
    return _linked_substrate_count(session, project_ids=project_ids, canonical_id=canonical_id) > 0
