"""Merge one person canonical into another (relink substrates, delete source)."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db import (
    BackfieldProject,
    StylebookPersonAlias,
    StylebookPersonCanonical,
    StylebookPersonMeta,
    SubstratePerson,
)
from backfield_events import record_canonical_merged, suppress_canonical_evidence_events
from sqlmodel import Session, col, func, select

from backfield_entities.connections.rewire import rewire_connections_for_canonical_merge
from backfield_entities.entities.person.persist import (
    link_substrate_to_canonical_atomic,
    upsert_alias_for_canonical_text,
)
from backfield_entities.entities.person.types import person_alias_lookup_keys


@dataclass(frozen=True)
class MergePersonCanonicalResult:
    source_id: str
    target_id: str
    relinked_substrate_count: int
    source_deleted: bool
    relinked_substrates: tuple[tuple[int, int], ...]
    transferred_alias_count: int
    transferred_meta_count: int
    person_type: str | None


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


def _meta_value(row: StylebookPersonMeta) -> tuple[object, ...]:
    return (
        row.value_type,
        row.value_text,
        row.value_number,
        row.value_boolean,
    )


def _preflight_meta_merge(
    session: Session,
    *,
    source_id: str,
    target_id: str,
) -> tuple[list[StylebookPersonMeta], dict[str, StylebookPersonMeta]]:
    source_rows = list(
        session.exec(
            select(StylebookPersonMeta).where(
                StylebookPersonMeta.stylebook_person_canonical_id == source_id
            )
        ).all()
    )
    target_rows = list(
        session.exec(
            select(StylebookPersonMeta).where(
                StylebookPersonMeta.stylebook_person_canonical_id == target_id
            )
        ).all()
    )
    target_by_type = {str(row.meta_type): row for row in target_rows}
    for source_row in source_rows:
        target_row = target_by_type.get(str(source_row.meta_type))
        if target_row is not None and _meta_value(source_row) != _meta_value(target_row):
            raise ValueError(
                f"person metadata conflict for {source_row.meta_type!r}; resolve it before merging"
            )
    return source_rows, target_by_type


def _transfer_aliases(
    session: Session,
    *,
    source: StylebookPersonCanonical,
    target: StylebookPersonCanonical,
    provenance: str,
) -> int:
    source_rows = list(
        session.exec(
            select(StylebookPersonAlias).where(
                StylebookPersonAlias.person_canonical_id == str(source.id)
            )
        ).all()
    )
    target_by_norm = {
        str(row.normalized_alias): row
        for row in session.exec(
            select(StylebookPersonAlias).where(
                StylebookPersonAlias.person_canonical_id == str(target.id)
            )
        ).all()
    }
    transferred = 0
    for source_alias in source_rows:
        normalized_alias = str(source_alias.normalized_alias)
        target_alias = target_by_norm.get(normalized_alias)
        if target_alias is None:
            source_alias.person_canonical_id = str(target.id)
            source_alias.provenance = provenance
            session.add(source_alias)
            target_by_norm[normalized_alias] = source_alias
            transferred += 1
            continue
        if not source_alias.suppressed:
            target_alias.suppressed = False
        session.add(target_alias)
        session.delete(source_alias)

    session.flush()
    for normalized_alias in person_alias_lookup_keys(str(source.label)):
        if normalized_alias in target_by_norm:
            continue
        upsert_alias_for_canonical_text(
            session,
            canon_id=str(target.id),
            alias_text=str(source.label),
            normalized_alias=normalized_alias,
            provenance=provenance,
        )
        transferred += 1
    session.flush()
    return transferred


def _alias_state(
    session: Session,
    *,
    canonical_id: str,
) -> dict[str, tuple[str, str, bool]]:
    rows = session.exec(
        select(StylebookPersonAlias).where(
            StylebookPersonAlias.person_canonical_id == canonical_id
        )
    ).all()
    return {
        str(row.normalized_alias): (
            str(row.alias_text),
            str(row.provenance),
            bool(row.suppressed),
        )
        for row in rows
    }


def _restore_alias_state(
    session: Session,
    *,
    canonical_id: str,
    state: dict[str, tuple[str, str, bool]],
) -> None:
    rows = session.exec(
        select(StylebookPersonAlias).where(
            StylebookPersonAlias.person_canonical_id == canonical_id,
            col(StylebookPersonAlias.normalized_alias).in_(state),
        )
    ).all()
    for row in rows:
        alias_text, provenance, suppressed = state[str(row.normalized_alias)]
        row.alias_text = alias_text
        row.provenance = provenance
        row.suppressed = suppressed
        session.add(row)


def _transfer_meta(
    session: Session,
    *,
    source_rows: list[StylebookPersonMeta],
    target_by_type: dict[str, StylebookPersonMeta],
    target_id: str,
) -> int:
    transferred = 0
    for source_row in source_rows:
        target_row = target_by_type.get(str(source_row.meta_type))
        if target_row is None:
            source_row.stylebook_person_canonical_id = target_id
            session.add(source_row)
            transferred += 1
            continue
        target_row.added = bool(target_row.added or source_row.added)
        target_row.edited = bool(target_row.edited or source_row.edited)
        session.add(target_row)
    return transferred


def _person_type_after_merge(
    *,
    source: StylebookPersonCanonical,
    target: StylebookPersonCanonical,
    resolved_person_type: str | None,
) -> str | None:
    resolved = (resolved_person_type or "").strip() or None
    if resolved is not None:
        return resolved
    source_type = (source.person_type or "").strip() or None
    target_type = (target.person_type or "").strip() or None
    non_standing_types = {"crime_justice_subject", "other", "unknown"}
    for person_type in (target_type, source_type):
        if person_type is not None and person_type not in non_standing_types:
            return person_type
    for person_type in (target_type, source_type):
        if person_type == "crime_justice_subject":
            return person_type
    return target_type or source_type


def merge_person_canonical_into(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    source_canonical_id: str,
    target_canonical_id: str,
    provenance: str = "stylebook_cleanup_merge",
    resolved_person_type: str | None = None,
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

    person_type = _person_type_after_merge(
        source=source,
        target=target,
        resolved_person_type=resolved_person_type,
    )
    source_meta, target_meta_by_type = _preflight_meta_merge(
        session,
        source_id=source_id,
        target_id=target_id,
    )
    # Move aliases and connections before relinking. Relinking the last
    # substrate can prune an ingest-only source canonical and cascade-delete
    # source-owned evidence before the merge can preserve it.
    transferred_alias_count = _transfer_aliases(
        session,
        source=source,
        target=target,
        provenance=provenance,
    )
    preserved_alias_state = _alias_state(session, canonical_id=target_id)

    # The merged event subsumes the per-substrate relink evidence events below.
    suppress_canonical_evidence_events(
        session,
        entity_type="person",
        canonical_ids=[source_id, target_id],
    )

    project_ids = _organization_project_ids(session, organization_id=organization_id)
    rewire_connections_for_canonical_merge(
        session,
        entity_type="person",
        source_canonical_id=source_id,
        target_canonical_id=target_id,
        project_ids=project_ids,
    )
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
    _restore_alias_state(
        session,
        canonical_id=target_id,
        state=preserved_alias_state,
    )

    remaining = _linked_substrate_count(
        session,
        project_ids=project_ids,
        canonical_id=source_id,
    )
    if remaining > 0:
        raise ValueError("source canonical still has linked people after merge")

    transferred_meta_count = _transfer_meta(
        session,
        source_rows=source_meta,
        target_by_type=target_meta_by_type,
        target_id=target_id,
    )
    target.public_figure = bool(target.public_figure or source.public_figure)
    target.title = target.title or source.title
    target.affiliation = target.affiliation or source.affiliation
    target.person_type = person_type
    target.sort_key = target.sort_key or source.sort_key
    if (
        target.primary_substrate_person_id is None
        and source.primary_substrate_person_id is not None
    ):
        target.primary_substrate_person_id = source.primary_substrate_person_id
    session.add(target)

    record_canonical_merged(
        session,
        stylebook_id=int(stylebook_id),
        entity_type="person",
        source_canonical_id=source_id,
        target_canonical_id=target_id,
        label=str(source.label),
    )
    session.delete(source)
    return MergePersonCanonicalResult(
        source_id=source_id,
        target_id=target_id,
        relinked_substrate_count=relinked,
        source_deleted=True,
        relinked_substrates=tuple(relinked_substrates),
        transferred_alias_count=transferred_alias_count,
        transferred_meta_count=transferred_meta_count,
        person_type=person_type,
    )


def canonical_has_linked_evidence(
    session: Session,
    *,
    organization_id: int,
    canonical_id: str,
) -> bool:
    project_ids = _organization_project_ids(session, organization_id=organization_id)
    return _linked_substrate_count(session, project_ids=project_ids, canonical_id=canonical_id) > 0
