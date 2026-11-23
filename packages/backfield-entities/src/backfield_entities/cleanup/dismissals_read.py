"""Read access to cleanup dismissals for keyed clients.

Reason, run and actor-run attribution arrive with the apply ledger; today a dismissal records the
check, the pair (or single canonical) and who made it and when.
"""

from __future__ import annotations

from datetime import datetime

from backfield_db import StylebookCleanupDismissal
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
    created_at: datetime


class DismissalPage(BaseModel):
    items: list[DismissalItem]
    next_cursor: str | None = None


class DismissalsCursor(BaseModel):
    after_id: int


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
    return DismissalPage(
        items=[
            DismissalItem(
                id=int(row.id),
                check_id=str(row.check_id),
                pair_key=str(row.pair_key),
                canonical_ids=[part for part in str(row.pair_key).split("|") if part],
                created_by_user_id=row.created_by_user_id,
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
