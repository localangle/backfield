"""Immutable per-Stylebook slug allocation for location canonical rows."""

from __future__ import annotations

import re

from backfield_db import StylebookLocationCanonical
from sqlmodel import Session, col, select


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
