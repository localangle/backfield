"""Immutable per-Stylebook slug allocation for canonical rows."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TypeVar

from backfield_db import StylebookLocationCanonical
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

T = TypeVar("T")

_MAX_SLUG_ALLOCATION_ATTEMPTS = 8

_STYLEBOOK_CANONICAL_SLUG_CONSTRAINT_MARKERS = (
    "uq_stylebook_person_canonical_stylebook_slug",
    "uq_stylebook_organization_canonical_stylebook_slug",
    "uq_stylebook_location_canonical_stylebook_slug",
)


def _slugify_label(label: str) -> str:
    """Match ``_slugify`` in ``stylebook_api.routers.stylebooks`` (lowercase, hyphens)."""
    s = label.lower().strip().replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "location"


def allocate_unique_canonical_slug(session: Session, *, stylebook_id: int, label: str) -> str:
    """Allocate a unique slug per stylebook; add ``-2``, ``-3``, … suffixes on collision."""
    base = _slugify_label(label)
    slug = base
    n = 2
    while True:
        hit = session.exec(
            select(StylebookLocationCanonical.id).where(
                StylebookLocationCanonical.stylebook_id == stylebook_id,
                col(StylebookLocationCanonical.slug) == slug,
            )
        ).first()
        if hit is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


def is_stylebook_canonical_slug_unique_violation(exc: BaseException) -> bool:
    """True when ``exc`` is a per-stylebook canonical slug unique constraint failure."""
    parts: list[str] = [str(exc)]
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        parts.append(str(cause))
    orig = getattr(exc, "orig", None)
    if orig is not None:
        parts.append(str(orig))
    text = " ".join(parts)
    if any(marker in text for marker in _STYLEBOOK_CANONICAL_SLUG_CONSTRAINT_MARKERS):
        return True
    # SQLite reports ``UNIQUE constraint failed: <table>.stylebook_id, <table>.slug``.
    if "UNIQUE constraint failed" in text and "stylebook_" in text and ".slug" in text:
        return True
    return False


def flush_new_canonical_with_slug_retry(
    session: Session,
    *,
    stylebook_id: int,
    label: str,
    allocate_slug: Callable[[Session, int, str], str],
    build_row: Callable[[str], T],
) -> T:
    """Insert a canonical row, retrying when concurrent ingest claims the same slug."""
    clean = label.strip()
    if not clean:
        raise ValueError("label is required")
    last_exc: IntegrityError | None = None
    for _ in range(_MAX_SLUG_ALLOCATION_ATTEMPTS):
        slug = allocate_slug(session, stylebook_id, clean)
        row = build_row(slug)
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
            return row
        except IntegrityError as exc:
            if not is_stylebook_canonical_slug_unique_violation(exc):
                raise
            last_exc = exc
    raise RuntimeError(
        f"Failed to allocate a unique Stylebook canonical slug for {clean!r} "
        f"after {_MAX_SLUG_ALLOCATION_ATTEMPTS} attempts"
    ) from last_exc
