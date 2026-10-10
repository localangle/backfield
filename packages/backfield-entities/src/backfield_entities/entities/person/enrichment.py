"""Reuse and store Wikidata and Wikipedia links on person records.

The enrich node reads existing Stylebook metadata. Persistence writes those links
onto empty metadata and onto the stored person. Neither path overwrites a value
that is already set.
"""

from __future__ import annotations

from typing import Any

from backfield_db import StylebookPersonMeta, SubstratePerson
from sqlmodel import Session, col, select

from backfield_entities.entities.person.policy import strong_identity_person_canonical_ids
from backfield_entities.entities.person.types import normalize_person_text

WIKIDATA_LINK_KEY = "wikidata_id"
WIKIPEDIA_LINK_KEY = "wikipedia_url"
WIKIDATA_META_TYPE = "wikidata"
WIKIPEDIA_META_TYPE = "wikipedia"

_LINK_TO_META: tuple[tuple[str, str], ...] = (
    (WIKIDATA_LINK_KEY, WIKIDATA_META_TYPE),
    (WIKIPEDIA_LINK_KEY, WIKIPEDIA_META_TYPE),
)


def enrichment_links_from_mapping(data: dict[str, Any] | None) -> dict[str, str]:
    """Return present Wikidata and Wikipedia links from a person payload."""
    if not isinstance(data, dict):
        return {}
    links: dict[str, str] = {}
    for key, _meta_type in _LINK_TO_META:
        raw = data.get(key)
        if isinstance(raw, str) and raw.strip():
            links[key] = raw.strip()
    return links


def enrichment_details_from_entry(entry: dict[str, Any]) -> dict[str, str]:
    """Links to merge into stored person details. Absent keys are left alone."""
    return enrichment_links_from_mapping(entry)


def cached_selected_links(
    session: Session,
    *,
    stylebook_id: int,
    name: str,
    affiliation: str | None,
    sources: set[str],
    project_id: int,
) -> dict[str, str] | None:
    """Copy links when exactly one canonical already has every selected source.

    Returns None when there is no unique match, or that match is missing a
    selected link. Callers then look the person up outside Stylebook.
    """
    selected = {source for source in sources if source in {WIKIDATA_META_TYPE, WIKIPEDIA_META_TYPE}}
    if not selected or not (name or "").strip():
        return None
    probe = SubstratePerson(
        project_id=project_id,
        name=name.strip(),
        normalized_name=normalize_person_text(name),
        affiliation=affiliation,
    )
    matches = strong_identity_person_canonical_ids(
        session,
        stylebook_id=stylebook_id,
        person=probe,
    )
    if len(matches) != 1:
        return None
    stored = _meta_text_by_type(session, canonical_id=matches[0])
    links: dict[str, str] = {}
    for link_key, meta_type in _LINK_TO_META:
        if meta_type not in selected:
            continue
        value = stored.get(meta_type)
        if not value:
            return None
        links[link_key] = value
    return links


def fill_empty_person_enrichment_from_substrate(
    session: Session,
    person: SubstratePerson,
) -> None:
    """Fill empty canonical metadata from links stored on the person."""
    canonical_id = person.stylebook_person_canonical_id
    if canonical_id is None or person.project_id is None:
        return
    details = person.source_details_json if isinstance(person.source_details_json, dict) else {}
    links = enrichment_links_from_mapping(details)
    if not links:
        return
    fill_empty_person_enrichment_meta(
        session,
        project_id=int(person.project_id),
        canonical_id=str(canonical_id),
        links=links,
    )


def fill_empty_person_enrichment_meta(
    session: Session,
    *,
    project_id: int,
    canonical_id: str,
    links: dict[str, str],
) -> None:
    """Insert text metadata for links the canonical does not already have."""
    for link_key, meta_type in _LINK_TO_META:
        value = links.get(link_key)
        if not value:
            continue
        existing = session.exec(
            select(StylebookPersonMeta).where(
                StylebookPersonMeta.stylebook_person_canonical_id == canonical_id,
                StylebookPersonMeta.meta_type == meta_type,
            )
        ).first()
        if existing is not None and (existing.value_text or "").strip():
            continue
        if existing is None:
            session.add(
                StylebookPersonMeta(
                    project_id=project_id,
                    stylebook_person_canonical_id=canonical_id,
                    meta_type=meta_type,
                    value_type="text",
                    value_text=value,
                )
            )
        else:
            existing.value_text = value
            existing.value_type = "text"
            session.add(existing)
    session.flush()


def _meta_text_by_type(session: Session, *, canonical_id: str) -> dict[str, str]:
    rows = session.exec(
        select(StylebookPersonMeta).where(
            StylebookPersonMeta.stylebook_person_canonical_id == canonical_id,
            col(StylebookPersonMeta.meta_type).in_([WIKIDATA_META_TYPE, WIKIPEDIA_META_TYPE]),
        )
    ).all()
    found: dict[str, str] = {}
    for row in rows:
        text = (row.value_text or "").strip()
        if text:
            found[str(row.meta_type)] = text
    return found
