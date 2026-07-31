"""Shared normalized user lookup helpers."""

from __future__ import annotations

from sqlalchemy import func
from sqlmodel import Session, select

from backfield_db.models import BackfieldUser


def normalize_user_email(email: str) -> str:
    return email.strip().lower()


def users_by_normalized_email(
    session: Session,
    email: str,
) -> list[BackfieldUser]:
    """Return every legacy-compatible match; callers must handle ambiguity."""
    normalized = normalize_user_email(email)
    return list(
        session.exec(
            select(BackfieldUser).where(
                func.lower(func.trim(BackfieldUser.email)) == normalized
            )
        ).all()
    )
