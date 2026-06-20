"""Cooperative stop checks for Stylebook background AI review runs."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

AI_REVIEW_STATUS_CANCELLED = "cancelled"


def ai_review_status_is_cancelled(status: str | None) -> bool:
    return str(status or "").strip() == AI_REVIEW_STATUS_CANCELLED


def load_review_status(engine: Any, *, model: type[Any], review_id: str) -> str | None:
    with Session(engine) as session:
        review = session.get(model, review_id)
        if review is None:
            return None
        return str(review.status)
