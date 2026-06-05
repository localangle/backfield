"""Enrich processed-item ``merged_people`` with persisted person and Stylebook link metadata."""

from __future__ import annotations

import copy
import re
from typing import Any

from api.processed_item.mention_occurrences import (
    build_mention_occurrences_for_row,
)
from backfield_db import (
    Stylebook,
    StylebookPersonCanonical,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.entities.person.types import person_identity_fingerprint
from sqlmodel import Session, col, select

_WS_RE = re.compile(r"\s+")


def _normalize_name(value: str) -> str:
    return _WS_RE.sub(" ", value.strip().lower())


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _identity_keys(person: Any, anchor: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(anchor, str) and anchor.strip():
        keys.add(anchor.strip())
    if not isinstance(person, dict):
        return keys
    for field in ("id", "mention_id"):
        raw = person.get(field)
        if raw is None or raw == "":
            continue
        value = str(raw).strip()
        if value:
            keys.add(value)
    name = person.get("name")
    title = _optional_text(person.get("title"))
    affiliation = _optional_text(person.get("affiliation"))
    if isinstance(name, str) and name.strip():
        fp = person_identity_fingerprint(
            normalized_name=_normalize_name(name),
            title=title,
            affiliation=affiliation,
        )
        keys.add(f"fingerprint:{fp}")
    return keys


def _apply_mention_editorial_to_person(
    person: dict[str, Any],
    mention: SubstratePersonMention,
) -> dict[str, Any]:
    out = copy.deepcopy(person)
    role = mention.role_in_story
    if isinstance(role, str) and role.strip():
        out["role_in_story"] = role.strip()
    nature = mention.nature
    if isinstance(nature, str) and nature.strip():
        out["nature"] = nature.strip()
    tags = mention.nature_secondary_tags_json
    if isinstance(tags, list) and tags:
        out["nature_secondary_tags"] = copy.deepcopy(tags)
    return out


def _load_occurrences_by_mention_id(
    session: Session,
    *,
    mention_ids: list[int],
) -> dict[int, list[SubstratePersonMentionOccurrence]]:
    if not mention_ids:
        return {}
    rows = session.exec(
        select(SubstratePersonMentionOccurrence)
        .where(col(SubstratePersonMentionOccurrence.person_mention_id).in_(mention_ids))
        .order_by(
            col(SubstratePersonMentionOccurrence.person_mention_id),
            col(SubstratePersonMentionOccurrence.occurrence_order).asc().nulls_last(),
            col(SubstratePersonMentionOccurrence.id),
        )
    ).all()
    out: dict[int, list[SubstratePersonMentionOccurrence]] = {}
    for row in rows:
        mid = int(row.person_mention_id)
        out.setdefault(mid, []).append(row)
    return out


def _load_mentions_by_person_for_article(
    session: Session,
    *,
    article_id: int | None,
) -> dict[int, SubstratePersonMention]:
    if article_id is None:
        return {}
    rows = session.exec(
        select(SubstratePersonMention).where(
            SubstratePersonMention.article_id == article_id,
            col(SubstratePersonMention.deleted).is_(False),
        )
    ).all()
    return {int(m.person_id): m for m in rows}


def _index_substrate_people(
    people: list[SubstratePerson],
    *,
    run_id: str,
) -> dict[str, SubstratePerson]:
    by_key: dict[str, SubstratePerson] = {}
    for person in people:
        details = person.source_details_json if isinstance(person.source_details_json, dict) else {}
        if str(details.get("run_id") or "") != run_id:
            continue
        raw_entry_id = details.get("raw_entry_id")
        if raw_entry_id is not None and raw_entry_id != "":
            by_key[str(raw_entry_id)] = person
        fp = person.identity_fingerprint
        if isinstance(fp, str) and fp.strip():
            by_key[f"fingerprint:{fp.strip()}"] = person
    return by_key


def _load_substrate_people_for_review(
    session: Session,
    *,
    project_id: int,
    run_id: str,
    article_id: int | None,
) -> dict[str, SubstratePerson]:
    if project_id <= 0:
        return {}
    person_ids: list[int] = []
    if article_id is not None:
        mentions = session.exec(
            select(SubstratePersonMention).where(
                SubstratePersonMention.article_id == article_id,
                col(SubstratePersonMention.deleted).is_(False),
            )
        ).all()
        person_ids = [int(m.person_id) for m in mentions]
        if not person_ids:
            return {}
        rows = session.exec(
            select(SubstratePerson).where(
                col(SubstratePerson.id).in_(person_ids),
                SubstratePerson.project_id == project_id,
            )
        ).all()
        return _index_substrate_people(list(rows), run_id=run_id)

    rows = session.exec(
        select(SubstratePerson).where(SubstratePerson.project_id == project_id)
    ).all()
    return _index_substrate_people(list(rows), run_id=run_id)


def _load_canonicals_by_id(
    session: Session, canonical_ids: set[str]
) -> dict[str, StylebookPersonCanonical]:
    if not canonical_ids:
        return {}
    rows = session.exec(
        select(StylebookPersonCanonical).where(
            col(StylebookPersonCanonical.id).in_(list(canonical_ids))
        )
    ).all()
    return {str(row.id): row for row in rows}


def _load_stylebook_slugs_by_id(
    session: Session, stylebook_ids: set[int]
) -> dict[int, str]:
    if not stylebook_ids:
        return {}
    rows = session.exec(
        select(Stylebook).where(col(Stylebook.id).in_(list(stylebook_ids)))
    ).all()
    out: dict[int, str] = {}
    for row in rows:
        if row.id is not None:
            out[int(row.id)] = str(row.slug)
    return out


def _pick_substrate_for_keys(
    by_key: dict[str, SubstratePerson], keys: set[str]
) -> SubstratePerson | None:
    for key in keys:
        hit = by_key.get(key)
        if hit is not None:
            return hit
    return None


def _person_payload_from_substrate(person: SubstratePerson) -> dict[str, Any]:
    return {
        "id": f"user_person:{int(person.id)}" if person.id is not None else None,
        "name": str(person.name),
        "title": person.title,
        "affiliation": person.affiliation,
        "public_figure": bool(person.public_figure),
        "type": person.person_type,
        "sort_key": person.sort_key,
    }


def enrich_merged_people_for_review(
    session: Session,
    *,
    project_id: int,
    run_id: str,
    article_id: int | None,
    merged_people: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach persisted person identity and Stylebook link summary to merged people rows."""
    by_key = _load_substrate_people_for_review(
        session, project_id=project_id, run_id=run_id, article_id=article_id
    )
    mentions_by_person = _load_mentions_by_person_for_article(
        session, article_id=article_id
    )
    mention_ids = [int(m.id) for m in mentions_by_person.values() if m.id is not None]
    occurrences_by_mention_id = _load_occurrences_by_mention_id(
        session, mention_ids=mention_ids
    )
    if not by_key:
        return merged_people

    canonical_ids: set[str] = set()
    for person in by_key.values():
        cid = person.stylebook_person_canonical_id
        if cid and str(person.canonical_link_status) == CANONICAL_LINK_LINKED:
            canonical_ids.add(str(cid))
    canons = _load_canonicals_by_id(session, canonical_ids)
    stylebook_ids = {int(c.stylebook_id) for c in canons.values()}
    stylebook_slugs = _load_stylebook_slugs_by_id(session, stylebook_ids)

    enriched: list[dict[str, Any]] = []
    matched_person_ids: set[int] = set()
    for row in merged_people:
        out = copy.deepcopy(row)
        person_payload = out.get("person")
        keys = _identity_keys(person_payload, out.get("anchor"))
        substrate = _pick_substrate_for_keys(by_key, keys)
        if substrate is None or substrate.id is None:
            enriched.append(out)
            continue

        mention = mentions_by_person.get(int(substrate.id))
        matched_person_ids.add(int(substrate.id))
        has_active_story_mention = article_id is None or mention is not None
        if has_active_story_mention:
            out["persisted_person_id"] = int(substrate.id)
        cid = substrate.stylebook_person_canonical_id
        if (
            has_active_story_mention
            and cid
            and str(substrate.canonical_link_status) == CANONICAL_LINK_LINKED
        ):
            canon = canons.get(str(cid))
            out["stylebook_person_canonical_id"] = str(cid)
            if canon is not None:
                sb_slug = stylebook_slugs.get(int(canon.stylebook_id))
                if sb_slug:
                    out["stylebook_slug"] = sb_slug
                out["stylebook_link"] = {
                    "label": str(canon.label),
                }

        link_status = str(substrate.canonical_link_status or "")
        if has_active_story_mention and link_status:
            out["canonical_link_status"] = link_status

        if isinstance(person_payload, dict):
            if mention is None:
                mention = mentions_by_person.get(int(substrate.id))
            if mention is not None:
                person_payload = _apply_mention_editorial_to_person(person_payload, mention)
            db_rows: list[SubstratePersonMentionOccurrence] | None = None
            if mention is not None and mention.id is not None:
                db_rows = occurrences_by_mention_id.get(int(mention.id))
            mention_occurrences = build_mention_occurrences_for_row(
                place=person_payload,
                overlay_patch=None,
                db_rows=db_rows,
            )
            out["person"] = person_payload
            out["mention_occurrences"] = mention_occurrences
        enriched.append(out)

    for raw_entry_id, substrate in by_key.items():
        if substrate.id is None or int(substrate.id) in matched_person_ids:
            continue
        if raw_entry_id.startswith("fingerprint:"):
            continue
        mention = mentions_by_person.get(int(substrate.id))
        if article_id is not None and mention is None:
            continue
        person_payload = _person_payload_from_substrate(substrate)
        if mention is not None:
            person_payload = _apply_mention_editorial_to_person(person_payload, mention)
        db_rows: list[SubstratePersonMentionOccurrence] | None = None
        if mention is not None and mention.id is not None:
            db_rows = occurrences_by_mention_id.get(int(mention.id))
        mention_occurrences = build_mention_occurrences_for_row(
            place=person_payload,
            overlay_patch=None,
            db_rows=db_rows,
        )
        enriched.append(
            {
                "anchor": raw_entry_id,
                "source": "user",
                "node_id": None,
                "index_in_node": None,
                "stale": False,
                "person": person_payload,
                "mention_occurrences": mention_occurrences,
                "persisted_person_id": int(substrate.id),
            }
        )
    return enriched
