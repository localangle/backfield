"""Shared helpers for substrate-to-canonical name mismatch finders."""

from __future__ import annotations

from dataclasses import dataclass, field

from backfield_db import (
    BackfieldProject,
    StylebookLocationAlias,
    StylebookOrganizationAlias,
    StylebookPersonAlias,
)
from sqlmodel import Session, col, select

from backfield_entities.entities.location.catalog_provenance import (
    is_location_catalog_editorial_provenance,
)
from backfield_entities.entities.organization.catalog_provenance import (
    is_organization_catalog_editorial_provenance,
)
from backfield_entities.entities.person.catalog_provenance import (
    is_person_catalog_editorial_provenance,
)

MAX_MISMATCH_EXAMPLES = 3
LOCATION_NAME_MISMATCH_CHECK_ID = "mismatched-locations"
PERSON_NAME_MISMATCH_CHECK_ID = "mismatched-people"
ORGANIZATION_NAME_MISMATCH_CHECK_ID = "mismatched-organizations"
ORG_TRIGRAM_CANDIDATE_FLOOR = 0.30


@dataclass
class CanonicalMismatchAgg:
    count: int = 0
    examples: list[str] = field(default_factory=list)

    def record(self, substrate_name: str) -> None:
        self.count += 1
        clean = str(substrate_name or "").strip()
        if not clean:
            return
        if clean in self.examples:
            return
        if len(self.examples) >= MAX_MISMATCH_EXAMPLES:
            return
        self.examples.append(clean)


def organization_project_ids(session: Session, *, organization_id: int) -> list[int]:
    rows = session.exec(
        select(BackfieldProject.id).where(BackfieldProject.organization_id == organization_id)
    ).all()
    return [int(row) for row in rows if row is not None]


def load_person_editorial_alias_keys(
    session: Session,
    *,
    canonical_ids: list[str],
) -> dict[str, frozenset[str]]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(
            StylebookPersonAlias.person_canonical_id,
            StylebookPersonAlias.normalized_alias,
            StylebookPersonAlias.provenance,
        ).where(
            col(StylebookPersonAlias.person_canonical_id).in_(canonical_ids),
            StylebookPersonAlias.suppressed.is_(False),
        )
    ).all()
    out: dict[str, set[str]] = {}
    for canon_id, norm, provenance in rows:
        if canon_id is None or not norm:
            continue
        if not is_person_catalog_editorial_provenance(provenance):
            continue
        cid = str(canon_id)
        out.setdefault(cid, set()).add(str(norm).strip())
    return {cid: frozenset(keys) for cid, keys in out.items()}


def load_location_editorial_alias_keys(
    session: Session,
    *,
    canonical_ids: list[str],
) -> dict[str, frozenset[str]]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(
            StylebookLocationAlias.location_canonical_id,
            StylebookLocationAlias.normalized_alias,
            StylebookLocationAlias.provenance,
        ).where(
            col(StylebookLocationAlias.location_canonical_id).in_(canonical_ids),
            StylebookLocationAlias.suppressed.is_(False),
        )
    ).all()
    out: dict[str, set[str]] = {}
    for canon_id, norm, provenance in rows:
        if canon_id is None or not norm:
            continue
        if not is_location_catalog_editorial_provenance(provenance):
            continue
        cid = str(canon_id)
        out.setdefault(cid, set()).add(str(norm).strip())
    return {cid: frozenset(keys) for cid, keys in out.items()}


def load_organization_editorial_alias_keys(
    session: Session,
    *,
    canonical_ids: list[str],
) -> dict[str, frozenset[str]]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(
            StylebookOrganizationAlias.organization_canonical_id,
            StylebookOrganizationAlias.normalized_alias,
            StylebookOrganizationAlias.provenance,
        ).where(
            col(StylebookOrganizationAlias.organization_canonical_id).in_(canonical_ids),
            StylebookOrganizationAlias.suppressed.is_(False),
        )
    ).all()
    out: dict[str, set[str]] = {}
    for canon_id, norm, provenance in rows:
        if canon_id is None or not norm:
            continue
        if not is_organization_catalog_editorial_provenance(provenance):
            continue
        cid = str(canon_id)
        out.setdefault(cid, set()).add(str(norm).strip())
    return {cid: frozenset(keys) for cid, keys in out.items()}
