"""Location mention aggregates, occurrences, and suppression for substrate persistence."""

from __future__ import annotations

from typing import Any

from agate_nodes.place_extract.mentions import mention_texts_for_persist
from backfield_db import (
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from backfield_stylebook.substrate_canonical_link_actions import (
    dispose_orphan_substrate_without_requeue,
)
from sqlalchemy import func
from sqlmodel import Session, col, select

from worker.substrate.common import _WS_RE, _utcnow
from worker.substrate.entities.location.span import _find_mention_span
from worker.substrate.entities.location.upsert import _display_name_for_place_entry

# Primary editorial role (PlaceExtract `nature`). Extras: `nature_secondary_tags` in extraction JSON
# → `SubstrateLocationMention.nature_secondary_tags_json`.
_NATURE_PRIMARY_ALLOWED = frozenset(
    {"primary", "secondary", "subject", "context", "person", "unknown"}
)
_NATURE_PRIMARY_SYNONYMS: dict[str, str] = {
    "setting": "primary",
    "main": "primary",
    "scene": "primary",
    "dateline": "primary",
}

_USER_OCCURRENCE_SOURCE_KINDS = frozenset({"user_edit", "user_review"})


def _normalize_nature_primary(entry: dict[str, Any]) -> str | None:
    raw = entry.get("nature")
    if not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if not s:
        return None
    if s in _NATURE_PRIMARY_ALLOWED:
        return s
    return _NATURE_PRIMARY_SYNONYMS.get(s, "unknown")


def _parse_nature_secondary_tags(entry: dict[str, Any]) -> list[str]:
    raw = entry.get("nature_secondary_tags")
    if raw is None:
        raw = entry.get("nature_secondary")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw:
        if isinstance(x, str):
            t = _WS_RE.sub(" ", x.strip()).lower()
            if t:
                out.append(t)
    seen: set[str] = set()
    uniq: list[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def retire_stale_article_mentions_for_rerun(
    session: Session,
    *,
    article_id: int,
    touched_location_ids: set[int],
) -> tuple[int, set[int]]:
    """Soft-delete pipeline mentions for this article superseded by a newer ingest.

    Keeps mentions for ``touched_location_ids`` (current ingest) and user-edited rows.
    Returns ``(mentions_retired, location_ids_with_retired_mentions)``.
    """
    mentions = session.exec(
        select(SubstrateLocationMention).where(
            col(SubstrateLocationMention.article_id) == article_id,
            col(SubstrateLocationMention.deleted).is_(False),
        )
    ).all()
    retired = 0
    retired_location_ids: set[int] = set()
    now = _utcnow()
    for mention in mentions:
        lid = int(mention.location_id)
        if lid in touched_location_ids:
            continue
        if mention.edited or mention.added:
            continue
        sk = str(mention.source_kind or "").strip()
        if sk and sk != "agate_geocode":
            continue
        mention.deleted = True
        mention.updated_at = now
        session.add(mention)
        retired += 1
        retired_location_ids.add(lid)
    if retired:
        session.flush()
    return retired, retired_location_ids


def dispose_orphan_substrates_after_retired_mentions(
    session: Session,
    *,
    project_id: int,
    location_ids: set[int],
    provenance: str = "agate_superseded_ingest",
) -> int:
    """Unlink (without re-queue) and delete substrate rows with no active mentions left.

    Used after :func:`retire_stale_article_mentions_for_rerun` so superseded geocode
    identities do not remain linked on a canonical with an empty Mentions group.
    """
    if not location_ids:
        return 0
    disposed = 0
    for lid in location_ids:
        remaining = int(
            session.scalar(
                select(func.count())
                .select_from(SubstrateLocationMention)
                .where(
                    SubstrateLocationMention.location_id == int(lid),
                    SubstrateLocationMention.deleted == False,  # noqa: E712
                )
            )
            or 0
        )
        if remaining > 0:
            continue
        loc = session.get(SubstrateLocation, int(lid))
        if loc is None or int(loc.project_id) != int(project_id):
            continue
        dispose_orphan_substrate_without_requeue(
            session,
            location=loc,
            provenance=provenance,
        )
        disposed += 1
    return disposed


def _suppress_prior_system_occurrences_for_mention(
    session: Session,
    *,
    mention_id: int,
) -> None:
    """Soft-delete all prior system extraction occurrences before re-ingesting a fresh set."""
    rows = session.exec(
        select(SubstrateLocationMentionOccurrence).where(
            col(SubstrateLocationMentionOccurrence.location_mention_id) == mention_id,
            col(SubstrateLocationMentionOccurrence.suppressed).is_(False),
            col(SubstrateLocationMentionOccurrence.source_kind) == "system_extraction",
        )
    ).all()
    now = _utcnow()
    for row in rows:
        row.suppressed = True
        row.updated_at = now
        session.add(row)
    session.flush()


def _spans_for_mention_texts(
    *,
    article_text: str,
    mention_texts: list[str],
) -> list[tuple[str, tuple[int, int] | None]]:
    """Map each mention text to a span, advancing search for repeated identical strings."""
    results: list[tuple[str, tuple[int, int] | None]] = []
    search_from = 0
    for mention_text in mention_texts:
        span = _find_mention_span(
            haystack=article_text,
            needle=mention_text,
            search_from=search_from,
        )
        results.append((mention_text, span))
        if span is not None:
            search_from = max(search_from, span[1])
    return results


def _upsert_mention_and_occurrence(
    session: Session,
    *,
    article_id: int,
    location_id: int,
    article_text: str,
    entry: dict[str, Any],
    run_id: str,
    graph_id: str,
    bucket: str,
    preserve_editor_changes: bool = False,
) -> None:
    mention_texts = mention_texts_for_persist(entry)
    if not mention_texts:
        fallback = _display_name_for_place_entry(entry)
        if fallback:
            mention_texts = [fallback]

    description = entry.get("description")
    description_str = str(description).strip() if isinstance(description, str) else None
    if description_str == "":
        description_str = None

    role = entry.get("role_in_story")
    role_str = str(role).strip() if isinstance(role, str) else None
    if role_str == "":
        role_str = None
    if role_str is None:
        role_str = description_str

    nature_str = _normalize_nature_primary(entry)
    secondary_tags = _parse_nature_secondary_tags(entry)

    mention = session.exec(
        select(SubstrateLocationMention).where(
            col(SubstrateLocationMention.article_id) == article_id,
            col(SubstrateLocationMention.location_id) == location_id,
        )
    ).first()

    needs_review = bucket == "needs_review" or entry.get("geocoded") is False
    review_data: dict[str, Any] | None = None
    if needs_review:
        review_data = {
            "bucket": bucket,
            "entry": entry,
        }

    now = _utcnow()
    if mention is None:
        mention = SubstrateLocationMention(
            article_id=article_id,
            location_id=location_id,
            role_in_story=role_str,
            nature=nature_str,
            nature_secondary_tags_json=secondary_tags,
            needs_review=bool(needs_review),
            review_data_json=review_data,
            source_kind="agate_geocode",
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
        mention.source_kind = "agate_geocode"
        mention.source_details_json = {"run_id": run_id, "graph_id": graph_id}
        mention.updated_at = now
        session.add(mention)
        session.flush()

    _suppress_prior_system_occurrences_for_mention(
        session,
        mention_id=int(mention.id),
    )

    source_details = {"run_id": run_id, "graph_id": graph_id, "places_bucket": bucket}
    for order, (mention_text, span) in enumerate(_spans_for_mention_texts(
        article_text=article_text,
        mention_texts=mention_texts,
    )):
        occurrence = SubstrateLocationMentionOccurrence(
            location_mention_id=int(mention.id),
            source_kind="system_extraction",
            source_details_json=source_details,
            mention_text=mention_text,
            quote_text=None,
            start_char=span[0] if span else None,
            end_char=span[1] if span else None,
            occurrence_order=order,
            labels_json=[],
            suppressed=False,
        )
        session.add(occurrence)
    session.flush()
