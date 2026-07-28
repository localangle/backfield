"""Load editor-approved canonical aliases for link validation and quality checks."""

from __future__ import annotations

from collections.abc import Callable

from backfield_db import (
    StylebookLocationAlias,
    StylebookOrganizationAlias,
    StylebookPersonAlias,
)
from sqlmodel import Session, col, select


def _editorial_alias_keys(
    rows: list[tuple[str | None, str | None, str | None]],
    *,
    is_editorial_provenance: Callable[[str | None], bool],
) -> dict[str, frozenset[str]]:
    out: dict[str, set[str]] = {}
    for canonical_id, normalized_alias, provenance in rows:
        if canonical_id is None or not normalized_alias:
            continue
        if not is_editorial_provenance(provenance):
            continue
        out.setdefault(str(canonical_id), set()).add(str(normalized_alias).strip())
    return {canonical_id: frozenset(keys) for canonical_id, keys in out.items()}


def load_person_editorial_alias_keys(
    session: Session,
    *,
    canonical_ids: list[str],
) -> dict[str, frozenset[str]]:
    # Local imports avoid entity-package initialization cycles with canonical policy.
    from backfield_entities.entities.person.catalog_provenance import (
        is_person_catalog_editorial_provenance,
    )

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
    return _editorial_alias_keys(
        rows,
        is_editorial_provenance=is_person_catalog_editorial_provenance,
    )


def load_location_editorial_alias_keys(
    session: Session,
    *,
    canonical_ids: list[str],
) -> dict[str, frozenset[str]]:
    # Local imports avoid entity-package initialization cycles with canonical policy.
    from backfield_entities.entities.location.catalog_provenance import (
        is_location_catalog_editorial_provenance,
    )

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
    return _editorial_alias_keys(
        rows,
        is_editorial_provenance=is_location_catalog_editorial_provenance,
    )


def load_organization_editorial_alias_keys(
    session: Session,
    *,
    canonical_ids: list[str],
) -> dict[str, frozenset[str]]:
    # Local imports avoid entity-package initialization cycles with canonical policy.
    from backfield_entities.entities.organization.catalog_provenance import (
        is_organization_catalog_editorial_provenance,
    )

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
    return _editorial_alias_keys(
        rows,
        is_editorial_provenance=is_organization_catalog_editorial_provenance,
    )
