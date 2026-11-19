"""Merge one organization canonical into another (relink substrates, delete source)."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db import (
    BackfieldProject,
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    StylebookOrganizationMeta,
    SubstrateOrganization,
)
from backfield_events import record_canonical_merged, suppress_canonical_evidence_events
from sqlmodel import Session, col, func, select

from backfield_entities.connections.rewire import rewire_connections_for_canonical_merge
from backfield_entities.entities.organization.persist import (
    link_substrate_to_canonical_atomic,
    upsert_alias_for_canonical_text,
)
from backfield_entities.entities.organization.types import (
    GENERATED_ACRONYM_PROVENANCE,
    organization_alias_surface_form,
    organization_canonical_alias_entries,
)


@dataclass(frozen=True)
class MergeOrganizationCanonicalResult:
    source_id: str
    target_id: str
    relinked_substrate_count: int
    source_deleted: bool
    relinked_substrates: tuple[tuple[int, int], ...]
    transferred_alias_count: int
    transferred_meta_count: int
    organization_type: str | None


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
            .select_from(SubstrateOrganization)
            .where(
                col(SubstrateOrganization.project_id).in_(project_ids),
                SubstrateOrganization.stylebook_organization_canonical_id == canonical_id,
            )
        )
        or 0
    )


def _meta_value(row: StylebookOrganizationMeta) -> tuple[object, ...]:
    return (
        row.value_type,
        row.value_text,
        row.value_number,
        row.value_boolean,
    )


def _organization_type_after_merge(
    *,
    source: StylebookOrganizationCanonical,
    target: StylebookOrganizationCanonical,
    resolved_organization_type: str | None,
) -> str | None:
    source_type = (source.organization_type or "").strip() or None
    target_type = (target.organization_type or "").strip() or None
    resolved = (resolved_organization_type or "").strip() or None
    if resolved is not None:
        return resolved
    # Choosing the keeper is also the default taxonomy decision. Organization
    # types are noisy classification evidence and must not preserve an approved
    # duplicate as a second canonical merely because extraction classified it
    # differently. Callers can still override the keeper's type explicitly.
    return target_type or source_type


def _preflight_meta_merge(
    session: Session,
    *,
    source_id: str,
    target_id: str,
) -> tuple[list[StylebookOrganizationMeta], dict[str, StylebookOrganizationMeta]]:
    source_rows = list(
        session.exec(
            select(StylebookOrganizationMeta).where(
                StylebookOrganizationMeta.stylebook_organization_canonical_id == source_id
            )
        ).all()
    )
    target_rows = list(
        session.exec(
            select(StylebookOrganizationMeta).where(
                StylebookOrganizationMeta.stylebook_organization_canonical_id == target_id
            )
        ).all()
    )
    target_by_type = {str(row.meta_type): row for row in target_rows}
    for source_row in source_rows:
        target_row = target_by_type.get(str(source_row.meta_type))
        if target_row is not None and _meta_value(source_row) != _meta_value(target_row):
            raise ValueError(
                "organization metadata conflict for "
                f"{source_row.meta_type!r}; resolve it before merging"
            )
    return source_rows, target_by_type


def _transfer_aliases(
    session: Session,
    *,
    source: StylebookOrganizationCanonical,
    target: StylebookOrganizationCanonical,
    provenance: str,
) -> int:
    source_rows = list(
        session.exec(
            select(StylebookOrganizationAlias).where(
                StylebookOrganizationAlias.organization_canonical_id == str(source.id)
            )
        ).all()
    )
    target_norms = set(
        session.exec(
            select(StylebookOrganizationAlias.normalized_alias).where(
                StylebookOrganizationAlias.organization_canonical_id == str(target.id)
            )
        ).all()
    )
    source_norms = {str(row.normalized_alias) for row in source_rows}
    source_norms.update(
        norm for norm, _generated in organization_canonical_alias_entries(source.label)
    )
    transferred = len(source_norms - target_norms)

    for source_alias in source_rows:
        target_alias = session.exec(
            select(StylebookOrganizationAlias).where(
                StylebookOrganizationAlias.organization_canonical_id == str(target.id),
                StylebookOrganizationAlias.normalized_alias == source_alias.normalized_alias,
            )
        ).first()
        if target_alias is None:
            source_alias.organization_canonical_id = str(target.id)
            session.add(source_alias)
            continue
        if not source_alias.suppressed:
            upsert_alias_for_canonical_text(
                session,
                canon_id=str(target.id),
                alias_text=str(source_alias.alias_text),
                normalized_alias=str(source_alias.normalized_alias),
                provenance=str(source_alias.provenance),
            )
        session.delete(source_alias)

    session.flush()
    target_norms = set(
        session.exec(
            select(StylebookOrganizationAlias.normalized_alias).where(
                StylebookOrganizationAlias.organization_canonical_id == str(target.id)
            )
        ).all()
    )
    for normalized_alias, generated_acronym in organization_canonical_alias_entries(source.label):
        if normalized_alias in target_norms:
            continue
        upsert_alias_for_canonical_text(
            session,
            canon_id=str(target.id),
            alias_text=organization_alias_surface_form(str(source.label), normalized_alias),
            normalized_alias=normalized_alias,
            provenance=GENERATED_ACRONYM_PROVENANCE if generated_acronym else provenance,
        )
    return transferred


def _alias_state(
    session: Session,
    *,
    canonical_id: str,
) -> dict[str, tuple[str, str, bool]]:
    rows = session.exec(
        select(StylebookOrganizationAlias).where(
            StylebookOrganizationAlias.organization_canonical_id == canonical_id
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
        select(StylebookOrganizationAlias).where(
            StylebookOrganizationAlias.organization_canonical_id == canonical_id,
            col(StylebookOrganizationAlias.normalized_alias).in_(state),
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
    source_rows: list[StylebookOrganizationMeta],
    target_by_type: dict[str, StylebookOrganizationMeta],
    target_id: str,
) -> int:
    transferred = 0
    for source_row in source_rows:
        target_row = target_by_type.get(str(source_row.meta_type))
        if target_row is None:
            source_row.stylebook_organization_canonical_id = target_id
            session.add(source_row)
            transferred += 1
            continue
        target_row.added = bool(target_row.added or source_row.added)
        target_row.edited = bool(target_row.edited or source_row.edited)
        session.add(target_row)
        # The source canonical delete cascades this duplicate metadata row.
        # Leaving that single delete path avoids a PostgreSQL double-delete
        # warning while preserving the target row's editorial flags.
    return transferred


def merge_organization_canonical_into(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
    source_canonical_id: str,
    target_canonical_id: str,
    provenance: str = "stylebook_cleanup_merge",
    resolved_organization_type: str | None = None,
) -> MergeOrganizationCanonicalResult:
    source_id = str(source_canonical_id)
    target_id = str(target_canonical_id)
    if source_id == target_id:
        raise ValueError("source and target canonical must differ")

    source = session.get(StylebookOrganizationCanonical, source_id)
    target = session.get(StylebookOrganizationCanonical, target_id)
    if source is None or int(source.stylebook_id) != int(stylebook_id):
        raise ValueError("source canonical not in this stylebook")
    if target is None or int(target.stylebook_id) != int(stylebook_id):
        raise ValueError("target canonical not in this stylebook")

    organization_type = _organization_type_after_merge(
        source=source,
        target=target,
        resolved_organization_type=resolved_organization_type,
    )
    source_meta, target_meta_by_type = _preflight_meta_merge(
        session,
        source_id=source_id,
        target_id=target_id,
    )
    # Move aliases before relinking. Relinking the final substrate may prune an
    # ingest-only source canonical, whose PostgreSQL FK cascades would otherwise
    # delete source-only aliases before the merge can preserve them.
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
        entity_type="organization",
        canonical_ids=[source_id, target_id],
    )

    project_ids = _organization_project_ids(session, organization_id=organization_id)
    linked = list(
        session.exec(
            select(SubstrateOrganization).where(
                col(SubstrateOrganization.project_id).in_(project_ids),
                SubstrateOrganization.stylebook_organization_canonical_id == source_id,
            )
        ).all()
    )

    relinked = 0
    relinked_substrates: list[tuple[int, int]] = []
    for organization in linked:
        link_substrate_to_canonical_atomic(
            session,
            stylebook_id=int(stylebook_id),
            organization=organization,
            target_canonical_id=target_id,
            provenance=provenance,
        )
        relinked += 1
        if organization.id is not None and organization.project_id is not None:
            relinked_substrates.append((int(organization.project_id), int(organization.id)))
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
        raise ValueError("source canonical still has linked organizations after merge")

    rewire_connections_for_canonical_merge(
        session,
        entity_type="organization",
        source_canonical_id=source_id,
        target_canonical_id=target_id,
        project_ids=project_ids,
    )

    transferred_meta_count = _transfer_meta(
        session,
        source_rows=source_meta,
        target_by_type=target_meta_by_type,
        target_id=target_id,
    )
    target.organization_type = organization_type
    if (
        target.primary_substrate_organization_id is None
        and source.primary_substrate_organization_id is not None
    ):
        target.primary_substrate_organization_id = source.primary_substrate_organization_id
    session.add(target)

    record_canonical_merged(
        session,
        stylebook_id=int(stylebook_id),
        entity_type="organization",
        source_canonical_id=source_id,
        target_canonical_id=target_id,
        label=str(source.label),
    )
    session.delete(source)
    return MergeOrganizationCanonicalResult(
        source_id=source_id,
        target_id=target_id,
        relinked_substrate_count=relinked,
        source_deleted=True,
        relinked_substrates=tuple(relinked_substrates),
        transferred_alias_count=transferred_alias_count,
        transferred_meta_count=transferred_meta_count,
        organization_type=organization_type,
    )


def canonical_has_linked_evidence(
    session: Session,
    *,
    organization_id: int,
    canonical_id: str,
) -> bool:
    project_ids = _organization_project_ids(session, organization_id=organization_id)
    return _linked_substrate_count(session, project_ids=project_ids, canonical_id=canonical_id) > 0
