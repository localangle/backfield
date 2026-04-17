"""Location mention aggregates, occurrences, and suppression for substrate persistence."""

from __future__ import annotations

from typing import Any

from backfield_db import SubstrateLocationMention, SubstrateLocationMentionOccurrence
from sqlmodel import Session, col, select

from worker.substrate_common import _WS_RE, _utcnow
from worker.substrate_location import _display_name_for_place_entry
from worker.substrate_span import _find_mention_span

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

def _suppress_prior_system_occurrences(
    session: Session,
    *,
    mention_id: int,
    mention_text: str,
) -> None:
    rows = session.exec(
        select(SubstrateLocationMentionOccurrence).where(
            col(SubstrateLocationMentionOccurrence.location_mention_id) == mention_id,
            col(SubstrateLocationMentionOccurrence.mention_text) == mention_text,
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
    occurrence_order: int,
) -> None:
    original_text = entry.get("original_text")
    mention_text = str(original_text).strip() if isinstance(original_text, str) else ""
    if not mention_text:
        mention_text = _display_name_for_place_entry(entry)

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

    # `description` is editorial "why this place matters" context.
    # `role_in_story` is a compact label when PlaceExtract provides it.

    span = _find_mention_span(haystack=article_text, needle=mention_text)

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
            edited=True,
        )
        session.add(mention)
        session.flush()
    else:
        mention.role_in_story = role_str or mention.role_in_story
        mention.nature = nature_str or mention.nature
        mention.nature_secondary_tags_json = secondary_tags
        mention.needs_review = bool(needs_review)
        mention.review_data_json = review_data or mention.review_data_json
        mention.source_kind = "agate_geocode"
        mention.source_details_json = {"run_id": run_id, "graph_id": graph_id}
        mention.updated_at = now
        mention.edited = True
        session.add(mention)
        session.flush()

    _suppress_prior_system_occurrences(
        session,
        mention_id=int(mention.id),
        mention_text=mention_text,
    )

    occurrence = SubstrateLocationMentionOccurrence(
        location_mention_id=int(mention.id),
        source_kind="system_extraction",
        source_details_json={"run_id": run_id, "graph_id": graph_id, "places_bucket": bucket},
        mention_text=mention_text,
        quote_text=None,
        start_char=span[0] if span else None,
        end_char=span[1] if span else None,
        occurrence_order=occurrence_order,
        labels_json=[],
        suppressed=False,
    )
    session.add(occurrence)
    session.flush()
