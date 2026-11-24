"""Backfill `merged_into` redirects for merges made before redirects were recorded.

Merges made by hand or by the Stylebook app before the redirect table existed left no redirect, so
`resolution` could not follow their old ids. Every such merge did write a `cleanup_merge` activity
event, so the activity log says which id went where:

- Most events name the merged-away record (`entity_id`) and the survivor (`related_entity_id`).
- Agent maintenance events for organizations name the survivor (`entity_id`, also `target_id` in the
  payload) and every merged-away record (`source_ids` in the payload).

A redirect is only written when it is safe: the old record is gone, the survivor still exists in the
same Stylebook, and no redirect for that old id exists yet. When the survivor was itself merged
away later, the redirect points at the final survivor.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from typing import Any

from backfield_db import StylebookActivity, StylebookCanonicalRedirect
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from backfield_entities.activity import EVENT_CLEANUP_MERGE
from backfield_entities.cleanup.entity_models import ENTITY_NAMES, cleanup_entity_models
from backfield_entities.cleanup.redirects import MAX_REDIRECT_HOPS, record_redirect

SAMPLE_LIMIT = 10
EVENT_PAGE_SIZE = 2000

# (stylebook id, entity type) scopes ids; an id only means something inside one Stylebook.
Scope = tuple[int, str]


class BackfillCounts(BaseModel):
    merges_found: int = Field(default=0, description="Old ids named by merge events.")
    written: int = Field(default=0, description="Redirects written (would be, on a dry run).")
    already_present: int = 0
    old_record_still_exists: int = 0
    survivor_missing: int = 0
    cycles: int = 0


class BackfillReport(BaseModel):
    dry_run: bool
    counts: BackfillCounts = Field(default_factory=BackfillCounts)
    by_entity: dict[str, BackfillCounts] = Field(default_factory=dict)
    survivor_missing_samples: list[str] = Field(
        default_factory=list,
        description="A few old ids whose survivor no longer exists, for follow-up.",
    )


def _merge_pairs(event: StylebookActivity) -> Iterator[tuple[str, str]]:
    """The (old id, survivor id) pairs one merge event names."""
    payload: dict[str, Any] = event.payload_json if isinstance(event.payload_json, dict) else {}
    if str(payload.get("mode") or "apply") != "apply":
        return
    entity_id = str(event.entity_id or "")
    related_id = str(event.related_entity_id or "")
    if related_id:
        yield entity_id, related_id
        return
    source_ids = payload.get("source_ids")
    target_id = str(payload.get("target_id") or entity_id)
    if isinstance(source_ids, list):
        for source_id in source_ids:
            yield str(source_id), target_id


def _read_merge_events(
    session: Session, *, stylebook_id: int | None
) -> dict[Scope, dict[str, str]]:
    """Old id to the survivor it was merged into, per scope; a later event wins."""
    pairs: dict[Scope, dict[str, str]] = defaultdict(dict)
    last_id = 0
    while True:
        query = (
            select(StylebookActivity)
            .where(
                StylebookActivity.event_type == EVENT_CLEANUP_MERGE,
                col(StylebookActivity.entity_type).in_(
                    [cleanup_entity_models(name).singular for name in ENTITY_NAMES]
                ),
                StylebookActivity.id > last_id,
            )
            .order_by(col(StylebookActivity.id))
            .limit(EVENT_PAGE_SIZE)
        )
        if stylebook_id is not None:
            query = query.where(StylebookActivity.stylebook_id == stylebook_id)
        events = session.exec(query).all()
        if not events:
            return pairs
        for event in events:
            scope = (int(event.stylebook_id), str(event.entity_type))
            for old_id, new_id in _merge_pairs(event):
                if old_id and new_id and old_id != new_id:
                    pairs[scope][old_id] = new_id
        last_id = int(events[-1].id)  # type: ignore[arg-type]


def _live_canonical_ids(session: Session, scopes: set[Scope]) -> dict[Scope, set[str]]:
    live: dict[Scope, set[str]] = {}
    for name in ENTITY_NAMES:
        models = cleanup_entity_models(name)
        for stylebook_id in {sb for sb, kind in scopes if kind == models.singular}:
            rows = session.exec(
                select(models.canonical.id).where(models.canonical.stylebook_id == stylebook_id)
            ).all()
            live[(stylebook_id, models.singular)] = {str(row) for row in rows}
    return live


def _existing_redirect_olds(session: Session, scopes: set[Scope]) -> dict[Scope, set[str]]:
    existing: dict[Scope, set[str]] = defaultdict(set)
    for stylebook_id, entity_type in scopes:
        rows = session.exec(
            select(StylebookCanonicalRedirect.old_id).where(
                StylebookCanonicalRedirect.stylebook_id == stylebook_id,
                StylebookCanonicalRedirect.entity_type == entity_type,
            )
        ).all()
        existing[(stylebook_id, entity_type)] = {str(row) for row in rows}
    return existing


def _final_survivor(old_id: str, merged_into: dict[str, str], live: set[str]) -> str | None:
    """Follow merges from ``old_id`` to a live record; None on a cycle or a very long chain."""
    current = old_id
    for _ in range(MAX_REDIRECT_HOPS):
        next_id = merged_into.get(current)
        if next_id is None or next_id in live:
            return next_id
        current = next_id
    return None


def backfill_merge_redirects(
    session: Session, *, stylebook_id: int | None = None, dry_run: bool = True
) -> BackfillReport:
    """Write the missing redirects (or count them, on a dry run). The caller commits."""
    merged_into = _read_merge_events(session, stylebook_id=stylebook_id)
    scopes = set(merged_into)
    live_ids = _live_canonical_ids(session, scopes)
    redirected = _existing_redirect_olds(session, scopes)
    report = BackfillReport(dry_run=dry_run)

    for scope in sorted(scopes):
        sb_id, entity_type = scope
        counts = report.by_entity.setdefault(entity_type, BackfillCounts())
        for old_id in sorted(merged_into[scope]):
            counts.merges_found += 1
            if old_id in live_ids[scope]:
                counts.old_record_still_exists += 1
            elif old_id in redirected[scope]:
                counts.already_present += 1
            else:
                survivor = _final_survivor(old_id, merged_into[scope], live_ids[scope])
                if survivor is None:
                    _count_unresolved(report, counts, old_id, merged_into[scope])
                    continue
                counts.written += 1
                if not dry_run:
                    record_redirect(
                        session,
                        stylebook_id=sb_id,
                        entity_type=entity_type,
                        old_id=old_id,
                        new_id=survivor,
                    )
    for counts in report.by_entity.values():
        for field in BackfillCounts.model_fields:
            setattr(report.counts, field, getattr(report.counts, field) + getattr(counts, field))
    return report


def _count_unresolved(
    report: BackfillReport, counts: BackfillCounts, old_id: str, merged_into: dict[str, str]
) -> None:
    """Tell a cycle (or runaway chain) from a survivor that no longer exists."""
    current = old_id
    for _ in range(MAX_REDIRECT_HOPS):
        next_id = merged_into.get(current)
        if next_id is None:
            counts.survivor_missing += 1
            if len(report.survivor_missing_samples) < SAMPLE_LIMIT:
                report.survivor_missing_samples.append(old_id)
            return
        current = next_id
    counts.cycles += 1
