"""Person mention aggregates, occurrences, and suppression for substrate persistence."""

from __future__ import annotations

from typing import Any

from backfield_db import (
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_stylebook.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_UNLINKED,
)
from backfield_stylebook.entities.person.persist import unlink_substrate_from_canonical
from backfield_stylebook.entities.person.types import PERSON_NATURE_VALUES
from backfield_stylebook.resolve import resolve_stylebook_id_for_project_id
from sqlalchemy import func
from sqlmodel import Session, col, select

from worker.substrate.common import _WS_RE, _utcnow
from worker.substrate.entities.location.span import _find_mention_span
from worker.substrate.entities.person.upsert import _display_name_for_person_entry

_PERSON_EXTRACT_SOURCE_KIND = "person_extract"


def _normalize_person_nature(entry: dict[str, Any]) -> str | None:
    raw = entry.get("nature")
    if not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if not s:
        return None
    if s in PERSON_NATURE_VALUES:
        return s
    return "other"


def _parse_nature_secondary_tags(entry: dict[str, Any]) -> list[str]:
    raw = entry.get("nature_secondary_tags")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            tag = _WS_RE.sub(" ", item.strip()).lower()
            if tag and tag in PERSON_NATURE_VALUES:
                out.append(tag)
    seen: set[str] = set()
    uniq: list[str] = []
    for tag in out:
        if tag not in seen:
            seen.add(tag)
            uniq.append(tag)
    return uniq


def _mention_texts_from_entry(entry: dict[str, Any]) -> list[str]:
    mentions = entry.get("mentions")
    texts: list[str] = []
    if isinstance(mentions, list):
        for item in mentions:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
    if texts:
        return texts
    fallback = _display_name_for_person_entry(entry)
    return [fallback] if fallback else []


def _spans_for_entry_mentions(
    *,
    article_text: str,
    entry: dict[str, Any],
) -> list[tuple[str, tuple[int, int] | None, bool]]:
    """Map each mention payload to span and whether it is a direct quote."""
    results: list[tuple[str, tuple[int, int] | None, bool]] = []
    search_from = 0
    mentions = entry.get("mentions")
    if isinstance(mentions, list) and mentions:
        for item in mentions:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            mention_text = text.strip()
            span = _find_mention_span(
                haystack=article_text,
                needle=mention_text,
                search_from=search_from,
            )
            is_quote = bool(item.get("quote"))
            results.append((mention_text, span, is_quote))
            if span is not None:
                search_from = max(search_from, span[1])
        return results

    for mention_text in _mention_texts_from_entry(entry):
        span = _find_mention_span(
            haystack=article_text,
            needle=mention_text,
            search_from=search_from,
        )
        results.append((mention_text, span, False))
        if span is not None:
            search_from = max(search_from, span[1])
    return results


def retire_stale_article_mentions_for_rerun(
    session: Session,
    *,
    article_id: int,
    touched_person_ids: set[int],
) -> tuple[int, set[int]]:
    mentions = session.exec(
        select(SubstratePersonMention).where(
            col(SubstratePersonMention.article_id) == article_id,
            col(SubstratePersonMention.deleted).is_(False),
        )
    ).all()
    retired = 0
    retired_person_ids: set[int] = set()
    now = _utcnow()
    for mention in mentions:
        pid = int(mention.person_id)
        if pid in touched_person_ids:
            continue
        if mention.edited or mention.added:
            continue
        sk = str(mention.source_kind or "").strip()
        if sk and sk != _PERSON_EXTRACT_SOURCE_KIND:
            continue
        mention.deleted = True
        mention.updated_at = now
        session.add(mention)
        retired += 1
        retired_person_ids.add(pid)
    if retired:
        session.flush()
    return retired, retired_person_ids


def dispose_orphan_substrates_after_retired_mentions(
    session: Session,
    *,
    project_id: int,
    person_ids: set[int],
    provenance: str = "agate_superseded_ingest",
) -> int:
    if not person_ids:
        return 0
    disposed = 0
    for pid in person_ids:
        remaining = int(
            session.scalar(
                select(func.count())
                .select_from(SubstratePersonMention)
                .where(
                    SubstratePersonMention.person_id == int(pid),
                    SubstratePersonMention.deleted == False,  # noqa: E712
                )
            )
            or 0
        )
        if remaining > 0:
            continue
        person = session.get(SubstratePerson, int(pid))
        if person is None or int(person.project_id) != int(project_id):
            continue
        _dispose_orphan_substrate_without_requeue(
            session,
            person=person,
            provenance=provenance,
        )
        disposed += 1
    return disposed


def _dispose_orphan_substrate_without_requeue(
    session: Session,
    *,
    person: SubstratePerson,
    provenance: str,
) -> None:
    if person.id is None:
        raise ValueError("person must be persisted")

    st = str(person.canonical_link_status or "")
    if st == CANONICAL_LINK_LINKED and person.stylebook_person_canonical_id is not None:
        cid = person.stylebook_person_canonical_id
        try:
            stylebook_id = resolve_stylebook_id_for_project_id(session, int(person.project_id))
        except LookupError:
            stylebook_id = None
        if stylebook_id is not None:
            unlink_substrate_from_canonical(
                session,
                stylebook_id=int(stylebook_id),
                person=person,
                provenance=provenance,
                requeue_after_unlink=False,
            )
        else:
            person.stylebook_person_canonical_id = None
            person.canonical_link_status = CANONICAL_LINK_UNLINKED
            person.canonical_review_reasons_json = [
                {
                    "code": "removed_from_story",
                    "previous_canonical_id": str(cid),
                    "provenance": provenance,
                    "note": "stylebook_missing",
                }
            ]
            session.add(person)
    elif st == CANONICAL_LINK_PENDING and person.stylebook_person_canonical_id is not None:
        person.stylebook_person_canonical_id = None
        session.add(person)

    session.delete(person)


def _suppress_prior_system_occurrences_for_mention(
    session: Session,
    *,
    mention_id: int,
) -> None:
    rows = session.exec(
        select(SubstratePersonMentionOccurrence).where(
            col(SubstratePersonMentionOccurrence.person_mention_id) == mention_id,
            col(SubstratePersonMentionOccurrence.suppressed).is_(False),
            col(SubstratePersonMentionOccurrence.source_kind) == "system_extraction",
        )
    ).all()
    now = _utcnow()
    for row in rows:
        row.suppressed = True
        row.updated_at = now
        session.add(row)
    session.flush()


def _upsert_mention_and_occurrence(
    session: Session,
    *,
    article_id: int,
    person_id: int,
    article_text: str,
    entry: dict[str, Any],
    run_id: str,
    graph_id: str,
    bucket: str,
    preserve_editor_changes: bool = False,
) -> None:
    role = entry.get("role_in_story")
    role_str = str(role).strip() if isinstance(role, str) else None
    if role_str == "":
        role_str = None

    nature_str = _normalize_person_nature(entry)
    secondary_tags = _parse_nature_secondary_tags(entry)
    needs_review = bucket == "needs_review"

    mention = session.exec(
        select(SubstratePersonMention).where(
            col(SubstratePersonMention.article_id) == article_id,
            col(SubstratePersonMention.person_id) == person_id,
        )
    ).first()

    review_data: dict[str, Any] | None = None
    if needs_review:
        review_data = {"bucket": bucket, "entry": entry}

    now = _utcnow()
    if mention is None:
        mention = SubstratePersonMention(
            article_id=article_id,
            person_id=person_id,
            role_in_story=role_str,
            nature=nature_str,
            nature_secondary_tags_json=secondary_tags,
            needs_review=bool(needs_review),
            review_data_json=review_data,
            source_kind=_PERSON_EXTRACT_SOURCE_KIND,
            source_details_json={"run_id": run_id, "graph_id": graph_id},
            edited=False,
        )
        session.add(mention)
        session.flush()
    else:
        if preserve_editor_changes and not bool(mention.deleted) and (
            bool(mention.edited) or bool(mention.added)
        ):
            return
        mention.deleted = False
        mention.role_in_story = role_str or mention.role_in_story
        mention.nature = nature_str or mention.nature
        mention.nature_secondary_tags_json = secondary_tags
        mention.needs_review = bool(needs_review)
        mention.review_data_json = review_data or mention.review_data_json
        mention.source_kind = _PERSON_EXTRACT_SOURCE_KIND
        mention.source_details_json = {"run_id": run_id, "graph_id": graph_id}
        mention.updated_at = now
        session.add(mention)
        session.flush()

    _suppress_prior_system_occurrences_for_mention(
        session,
        mention_id=int(mention.id),  # type: ignore[arg-type]
    )

    source_details = {"run_id": run_id, "graph_id": graph_id, "people_bucket": bucket}
    for order, (mention_text, span, is_quote) in enumerate(
        _spans_for_entry_mentions(article_text=article_text, entry=entry)
    ):
        labels: list[str] = ["quote"] if is_quote else []
        occurrence = SubstratePersonMentionOccurrence(
            person_mention_id=int(mention.id),  # type: ignore[arg-type]
            source_kind="system_extraction",
            source_details_json=source_details,
            mention_text=mention_text,
            quote_text=mention_text if is_quote else None,
            start_char=span[0] if span else None,
            end_char=span[1] if span else None,
            occurrence_order=order,
            labels_json=labels,
            suppressed=False,
        )
        session.add(occurrence)
    session.flush()
