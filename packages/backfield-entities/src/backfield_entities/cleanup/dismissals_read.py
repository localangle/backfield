"""Read access to cleanup dismissals for keyed clients.

A dismissal records the check, the pair (or single canonical), who made it and when, and, when a
cleanup run made it, the reason the caller gave and the run (with the key behind it).
"""

from __future__ import annotations

from datetime import datetime

from backfield_db import StylebookCleanupDismissal, StylebookCleanupRun
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from backfield_entities.cleanup.cursor import decode_cursor, encode_cursor

DISMISSALS_DEFAULT_LIMIT = 200
DISMISSALS_MAX_LIMIT = 1000


class DismissalItem(BaseModel):
    id: int
    check_id: str
    pair_key: str
    canonical_ids: list[str] = Field(description="The canonicals the dismissal covers.")
    created_by_user_id: int | None
    reason_code: str | None = Field(
        default=None, description="Why it was set aside, as the caller gave it."
    )
    run_id: str | None = Field(default=None, description="The cleanup run that set it aside.")
    credential_label: str | None = Field(
        default=None, description="The key behind that run, when a run made the dismissal."
    )
    created_at: datetime


class DismissalPage(BaseModel):
    items: list[DismissalItem]
    next_cursor: str | None = None


class DismissalsCursor(BaseModel):
    after_id: int


def _run_credential_labels(session: Session, run_ids: list[str]) -> dict[str, str | None]:
    if not run_ids:
        return {}
    rows = session.exec(
        select(StylebookCleanupRun.id, StylebookCleanupRun.credential_label).where(
            col(StylebookCleanupRun.id).in_(set(run_ids))
        )
    ).all()
    return {str(run_id): label for run_id, label in rows}


def list_dismissals(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str | None,
    cursor: str | None,
    limit: int,
) -> DismissalPage:
    """One page of dismissals, oldest first. Raises ``InvalidCursorError`` on a bad cursor."""
    statement = select(StylebookCleanupDismissal).where(
        StylebookCleanupDismissal.stylebook_id == stylebook_id
    )
    if check_id:
        statement = statement.where(StylebookCleanupDismissal.check_id == check_id.strip())
    if cursor:
        after_id = decode_cursor(cursor, DismissalsCursor).after_id
        statement = statement.where(col(StylebookCleanupDismissal.id) > after_id)
    rows = list(
        session.exec(statement.order_by(col(StylebookCleanupDismissal.id)).limit(limit + 1)).all()
    )
    page = rows[:limit]
    run_labels = _run_credential_labels(session, [row.run_id for row in page if row.run_id])
    return DismissalPage(
        items=[
            DismissalItem(
                id=int(row.id),
                check_id=str(row.check_id),
                pair_key=str(row.pair_key),
                canonical_ids=[part for part in str(row.pair_key).split("|") if part],
                created_by_user_id=row.created_by_user_id,
                reason_code=row.reason_code,
                run_id=row.run_id,
                credential_label=run_labels.get(str(row.run_id)) if row.run_id else None,
                created_at=row.created_at,
            )
            for row in page
        ],
        next_cursor=(
            encode_cursor(DismissalsCursor(after_id=int(page[-1].id)))
            if len(rows) > limit
            else None
        ),
    )
