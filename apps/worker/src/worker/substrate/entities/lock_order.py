"""Lock shared substrate rows in one fixed order (ascending id) before persisting an article.

People, organizations and locations are shared across articles in a project. Persist used to lock
them one at a time in the order each article mentioned them and hold the locks until commit, so
two items that touched the same rows in a different order deadlocked (sometimes in cycles of four).
Taking the locks up front, always in ascending id order, makes the waits one-directional.

Locks use ``FOR NO KEY UPDATE`` (``with_for_update(key_share=True)``): other writers are still
excluded, but the ``FOR KEY SHARE`` that foreign-key checks take on these rows is not blocked.

Rows that do not exist yet are not locked here; concurrent inserts are handled by the
unique-violation fallbacks in the upserts.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from backfield_db import SubstrateLocation, SubstrateOrganization, SubstratePerson
from sqlalchemy import ColumnElement, and_, or_
from sqlalchemy.sql import Select
from sqlmodel import Session, col, select


def _ordered_lock_statement(
    id_column: Any, *conditions: ColumnElement[bool]
) -> Select[tuple[int | None]]:
    return select(id_column).where(*conditions).order_by(id_column).with_for_update(key_share=True)


def _lock_rows(session: Session, id_column: Any, *conditions: ColumnElement[bool]) -> None:
    session.exec(_ordered_lock_statement(id_column, *conditions)).all()


def lock_rows_in_id_order(session: Session, id_column: Any, ids: Iterable[int]) -> None:
    """Lock the given rows (by id) in ascending id order; use after commits released locks."""
    wanted = sorted({int(row_id) for row_id in ids})
    if not wanted:
        return
    _lock_rows(session, id_column, id_column.in_(wanted))


def lock_person_rows(session: Session, *, project_id: int, fingerprints: Iterable[str]) -> None:
    wanted = sorted(set(fingerprints))
    if not wanted:
        return
    _lock_rows(
        session,
        col(SubstratePerson.id),
        col(SubstratePerson.project_id) == project_id,
        col(SubstratePerson.identity_fingerprint).in_(wanted),
    )


def lock_organization_rows(
    session: Session, *, project_id: int, fingerprints: Iterable[str]
) -> None:
    wanted = sorted(set(fingerprints))
    if not wanted:
        return
    _lock_rows(
        session,
        col(SubstrateOrganization.id),
        col(SubstrateOrganization.project_id) == project_id,
        col(SubstrateOrganization.identity_fingerprint).in_(wanted),
    )


def lock_location_rows(
    session: Session,
    *,
    project_id: int,
    fingerprints: Iterable[str],
    external_identities: Iterable[tuple[str, str]],
) -> None:
    """Lock locations matching by identity fingerprint or by (external source, external id)."""
    wanted_fingerprints = sorted(set(fingerprints))
    matches: list[ColumnElement[bool]] = []
    if wanted_fingerprints:
        matches.append(col(SubstrateLocation.identity_fingerprint).in_(wanted_fingerprints))
    matches.extend(
        and_(
            col(SubstrateLocation.external_source) == source,
            col(SubstrateLocation.external_id) == external_id,
        )
        for source, external_id in sorted(set(external_identities))
    )
    if not matches:
        return
    _lock_rows(
        session,
        col(SubstrateLocation.id),
        col(SubstrateLocation.project_id) == project_id,
        or_(*matches),
    )
