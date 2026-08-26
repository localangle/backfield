"""Org/Stylebook custom connection natures beside the preferred code catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backfield_db import StylebookConnectionNatureCustom
from sqlmodel import Session, select

from backfield_entities.connections.natures import (
    all_preferred_natures,
    normalize_preferred_nature_slug,
)

NatureSource = Literal["preferred", "custom"]


@dataclass(frozen=True)
class NatureCatalogEntry:
    slug: str
    label: str
    source: NatureSource
    equivalent_to: str | None = None
    temporal_kind: str | None = None


def _normalize_slug(raw: str) -> str:
    return raw.strip().lower().replace(" ", "_")


def list_custom_natures(
    session: Session,
    *,
    stylebook_id: int,
) -> list[StylebookConnectionNatureCustom]:
    return list(
        session.exec(
            select(StylebookConnectionNatureCustom)
            .where(StylebookConnectionNatureCustom.stylebook_id == int(stylebook_id))
            .order_by(StylebookConnectionNatureCustom.slug)
        ).all()
    )


def merged_nature_catalog(
    session: Session,
    *,
    stylebook_id: int,
    q: str | None = None,
) -> list[NatureCatalogEntry]:
    """Preferred slugs (deduped) plus Stylebook customs, optionally filtered by ``q``."""
    query = (q or "").strip().lower()
    by_slug: dict[str, NatureCatalogEntry] = {}
    for nature in all_preferred_natures():
        if nature.slug in by_slug:
            continue
        by_slug[nature.slug] = NatureCatalogEntry(
            slug=nature.slug,
            label=nature.label,
            source="preferred",
            temporal_kind=nature.temporal_kind,
        )
    for custom in list_custom_natures(session, stylebook_id=stylebook_id):
        by_slug[custom.slug] = NatureCatalogEntry(
            slug=custom.slug,
            label=custom.label,
            source="custom",
            equivalent_to=custom.equivalent_to,
            temporal_kind=custom.temporal_kind,
        )
    entries = sorted(by_slug.values(), key=lambda e: e.slug)
    if not query:
        return entries
    return [
        entry
        for entry in entries
        if query in entry.slug or query in entry.label.casefold()
    ]


def get_custom_nature(
    session: Session,
    *,
    stylebook_id: int,
    slug: str,
) -> StylebookConnectionNatureCustom | None:
    normalized = _normalize_slug(slug)
    return session.exec(
        select(StylebookConnectionNatureCustom).where(
            StylebookConnectionNatureCustom.stylebook_id == int(stylebook_id),
            StylebookConnectionNatureCustom.slug == normalized,
        )
    ).first()


def is_known_nature_slug(
    session: Session,
    *,
    stylebook_id: int,
    slug: str | None,
) -> bool:
    if slug is None:
        return True
    normalized = normalize_preferred_nature_slug(slug) or _normalize_slug(slug)
    preferred_slugs = {n.slug for n in all_preferred_natures()}
    if normalized in preferred_slugs:
        return True
    return get_custom_nature(session, stylebook_id=stylebook_id, slug=normalized) is not None


def upsert_custom_nature(
    session: Session,
    *,
    stylebook_id: int,
    slug: str,
    label: str | None = None,
    equivalent_to: str | None = None,
    temporal_kind: str = "dynamic",
) -> StylebookConnectionNatureCustom:
    """Create or return an existing custom nature. Preferred slugs are not stored as customs."""
    normalized = _normalize_slug(slug)
    if not normalized:
        raise ValueError("nature slug is required")
    preferred_slugs = {n.slug for n in all_preferred_natures()}
    preferred = normalize_preferred_nature_slug(normalized) or normalized
    if preferred in preferred_slugs:
        raise ValueError("preferred natures cannot be stored as customs")

    existing = get_custom_nature(session, stylebook_id=stylebook_id, slug=normalized)
    if existing is not None:
        return existing

    display = (label or "").strip() or normalized.replace("_", " ")
    kind = (temporal_kind or "dynamic").strip().lower() or "dynamic"
    if kind not in {"static", "dynamic"}:
        kind = "dynamic"
    equiv = (equivalent_to or "").strip().lower() or None
    if equiv and equiv not in preferred_slugs:
        equiv = None

    row = StylebookConnectionNatureCustom(
        stylebook_id=int(stylebook_id),
        slug=normalized,
        label=display,
        equivalent_to=equiv,
        temporal_kind=kind,
    )
    session.add(row)
    session.flush()
    return row


def delete_custom_nature(
    session: Session,
    *,
    stylebook_id: int,
    slug: str,
) -> bool:
    row = get_custom_nature(session, stylebook_id=stylebook_id, slug=slug)
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def ensure_custom_nature_for_manual_slug(
    session: Session,
    *,
    stylebook_id: int,
    nature: str | None,
) -> str | None:
    """If ``nature`` is non-preferred, upsert a custom row and return the normalized slug."""
    if nature is None:
        return None
    preferred = normalize_preferred_nature_slug(nature)
    preferred_slugs = {n.slug for n in all_preferred_natures()}
    if preferred and preferred in preferred_slugs:
        return preferred
    normalized = _normalize_slug(nature)
    if not normalized:
        return None
    if normalized in preferred_slugs:
        return normalized
    upsert_custom_nature(
        session,
        stylebook_id=stylebook_id,
        slug=normalized,
        label=normalized.replace("_", " "),
    )
    return normalized
