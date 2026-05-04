"""Slug generation and allocation for Stylebook catalog rows (not location canonicals)."""

from __future__ import annotations

import re

from backfield_db import Stylebook, StylebookSlugRedirect
from sqlmodel import Session, select

# Conservative URL segment length (matches PRD / canonical_slug spirit).
_MAX_STYLEBOOK_SLUG_LEN = 100


def slugify_stylebook_name(name: str) -> str:
    """Lowercase ASCII slug from display name (hyphenated); empty input becomes ``stylebook``."""
    s = name.lower().strip().replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        s = "stylebook"
    if len(s) > _MAX_STYLEBOOK_SLUG_LEN:
        s = s[:_MAX_STYLEBOOK_SLUG_LEN].rstrip("-") or "stylebook"
    return s


def collect_reserved_slugs_for_org(session: Session, organization_id: int) -> set[str]:
    """Reserved slugs: current catalog slugs and historical redirect keys."""
    cur = session.exec(
        select(Stylebook.slug).where(Stylebook.organization_id == organization_id)
    ).all()
    prior = session.exec(
        select(StylebookSlugRedirect.old_slug).where(
            StylebookSlugRedirect.organization_id == organization_id
        )
    ).all()
    out: set[str] = set()
    for row in cur:
        if row is not None:
            out.add(str(row))
    for row in prior:
        if row is not None:
            out.add(str(row))
    return out


def allocate_unique_stylebook_slug(
    session: Session,
    organization_id: int,
    display_name: str,
    *,
    ignore_stylebook_id: int | None = None,
) -> str:
    """Return a slug unique within the org among current slugs and redirect history.

    When renaming an existing row, pass ``ignore_stylebook_id`` so its current slug is not
    treated as blocking the next candidate (the row will move off that slug).
    """
    base = slugify_stylebook_name(display_name)
    taken = collect_reserved_slugs_for_org(session, organization_id)
    if ignore_stylebook_id is not None:
        row = session.get(Stylebook, ignore_stylebook_id)
        if row is not None and row.slug is not None:
            taken.discard(str(row.slug))
    slug = base
    n = 2
    while slug in taken:
        suffix = f"-{n}"
        max_base = _MAX_STYLEBOOK_SLUG_LEN - len(suffix)
        truncated = base[:max_base].rstrip("-") if max_base > 0 else "sb"
        slug = f"{truncated}{suffix}"
        n += 1
    return slug
