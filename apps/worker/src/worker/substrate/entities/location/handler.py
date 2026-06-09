"""Location (places) persist handler for substrate orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backfield_db import SubstrateLocation, SubstrateLocationMention
from backfield_entities.canonical.link import CANONICAL_LINK_UNLINKED
from backfield_entities.canonical.plan_types import CanonicalPersistPlan
from backfield_entities.entities.location.persist import (
    apply_canonical_persist_plan,
    apply_canonical_persist_plan_review_only,
    refresh_aliases_for_linked_location,
)
from backfield_entities.entities.location.policy import (
    decide_location_canonical_persist_plan,
    plan_requires_llm_canonical_adjudication,
)
from sqlmodel import Session, col, select

from worker.substrate.canonical.adjudication import (
    LocationAdjudicationPrepared,
    prepare_location_adjudication,
    resolve_location_adjudication_plan,
    run_location_adjudication_llm,
)
from worker.substrate.canonical.parallel_llm import (
    canonical_adjudication_max_concurrent,
    run_callables_parallel,
)
from worker.substrate.entities.location.mentions import (
    _upsert_mention_and_occurrence,
    dispose_orphan_substrates_after_retired_mentions,
    retire_stale_article_mentions_for_rerun,
)
from worker.substrate.entities.location.upsert import _iter_place_entries, _upsert_location
from worker.substrate.entities.registry import (
    DomainReconciliationSummary,
    HandlerPersistResult,
    PersistContext,
    register_persist_handler,
)

logger = logging.getLogger(__name__)


@dataclass
class _PendingLocationAdjudication:
    location: SubstrateLocation
    bucket: str
    entry: dict[str, Any]
    plan: CanonicalPersistPlan
    prepared: LocationAdjudicationPrepared


def _active_mention_for_article_location(
    session: Session,
    *,
    article_id: int,
    location_id: int,
) -> Any | None:
    return session.exec(
        select(SubstrateLocationMention).where(
            SubstrateLocationMention.article_id == int(article_id),
            SubstrateLocationMention.location_id == int(location_id),
            col(SubstrateLocationMention.deleted).is_(False),
        )
    ).first()


def _editor_touched_mention(mention: Any | None) -> bool:
    return bool(mention is not None and (bool(mention.edited) or bool(mention.added)))


def _apply_location_plan_and_mention(
    session: Session,
    ctx: PersistContext,
    *,
    location: SubstrateLocation,
    bucket: str,
    entry: dict[str, Any],
    plan: CanonicalPersistPlan,
) -> None:
    if ctx.stylebook_id is None:
        return
    if ctx.settings.auto_apply_canonicalization:
        apply_canonical_persist_plan(
            session,
            stylebook_id=ctx.stylebook_id,
            location=location,
            plan=plan,
            places_bucket=bucket,
            provenance="substrate_ingest",
            auto_apply_canonicalization=True,
        )
    else:
        apply_canonical_persist_plan_review_only(
            session,
            stylebook_id=ctx.stylebook_id,
            location=location,
            plan=plan,
            places_bucket=bucket,
        )
    _upsert_mention_and_occurrence(
        session,
        article_id=int(ctx.article_id),
        location_id=int(location.id),
        article_text=ctx.article_text,
        entry=entry,
        run_id=ctx.run_id,
        graph_id=ctx.graph_id,
        bucket=bucket,
        preserve_editor_changes=ctx.policy == "smart_merge",
    )


class LocationPersistHandler:
    consolidated_key = "places"

    def persist(self, session: Session, ctx: PersistContext) -> HandlerPersistResult:
        places = ctx.consolidated.get("places")
        if not isinstance(places, dict):
            raise RuntimeError(
                "Location persist handler requires consolidated['places'] (GeocodeAgent output)"
            )

        policy = ctx.policy
        touched_location_ids: set[int] = set()
        added = 0
        updated = 0
        skipped = 0
        preserved = 0
        pending_adjudication: list[_PendingLocationAdjudication] = []
        adj_model = (ctx.settings.adjudication_model or "").strip() or "gpt-5-nano"
        ai_assisted = ctx.settings.canonicalization_mode == "ai_assisted"

        for bucket, entry in _iter_place_entries(places):
            upserted = _upsert_location(
                session,
                project_id=ctx.project_id,
                bucket=bucket,
                entry=entry,
                run_id=ctx.run_id,
                graph_id=ctx.graph_id,
                update_existing=policy != "add_only",
            )
            if upserted is None:
                continue
            loc = upserted.location
            active_mention = _active_mention_for_article_location(
                session,
                article_id=int(ctx.article_id),
                location_id=int(loc.id),
            )
            if policy == "add_only" and active_mention is not None:
                skipped += 1
                touched_location_ids.add(int(loc.id))
                continue
            if policy == "smart_merge" and _editor_touched_mention(active_mention):
                preserved += 1
                touched_location_ids.add(int(loc.id))
                continue
            if active_mention is None or upserted.created:
                added += 1
            elif upserted.updated:
                updated += 1
            if loc.id is not None:
                touched_location_ids.add(int(loc.id))
            if ctx.stylebook_id is not None and loc.stylebook_location_canonical_id is not None:
                refresh_aliases_for_linked_location(
                    session,
                    stylebook_id=ctx.stylebook_id,
                    location=loc,
                    provenance="substrate_ingest",
                )
                _upsert_mention_and_occurrence(
                    session,
                    article_id=int(ctx.article_id),
                    location_id=int(loc.id),
                    article_text=ctx.article_text,
                    entry=entry,
                    run_id=ctx.run_id,
                    graph_id=ctx.graph_id,
                    bucket=bucket,
                    preserve_editor_changes=policy == "smart_merge",
                )
            elif ctx.stylebook_id is not None:
                plan = decide_location_canonical_persist_plan(
                    session,
                    stylebook_id=ctx.stylebook_id,
                    places_bucket=bucket,
                    location=loc,
                    entry=entry,
                )
                needs_llm = ai_assisted and plan_requires_llm_canonical_adjudication(plan, loc)
                if needs_llm:
                    prepared = prepare_location_adjudication(
                        session,
                        plan=plan,
                        location=loc,
                        stylebook_id=ctx.stylebook_id,
                        model=adj_model,
                        model_config_id=ctx.settings.adjudication_ai_model_config_id,
                    )
                    if prepared is not None:
                        pending_adjudication.append(
                            _PendingLocationAdjudication(
                                location=loc,
                                bucket=bucket,
                                entry=entry,
                                plan=plan,
                                prepared=prepared,
                            )
                        )
                        continue
                _apply_location_plan_and_mention(
                    session,
                    ctx,
                    location=loc,
                    bucket=bucket,
                    entry=entry,
                    plan=plan,
                )
            elif loc.stylebook_location_canonical_id is None:
                loc.canonical_link_status = CANONICAL_LINK_UNLINKED
                session.add(loc)
                _upsert_mention_and_occurrence(
                    session,
                    article_id=int(ctx.article_id),
                    location_id=int(loc.id),
                    article_text=ctx.article_text,
                    entry=entry,
                    run_id=ctx.run_id,
                    graph_id=ctx.graph_id,
                    bucket=bucket,
                    preserve_editor_changes=policy == "smart_merge",
                )
            else:
                _upsert_mention_and_occurrence(
                    session,
                    article_id=int(ctx.article_id),
                    location_id=int(loc.id),
                    article_text=ctx.article_text,
                    entry=entry,
                    run_id=ctx.run_id,
                    graph_id=ctx.graph_id,
                    bucket=bucket,
                    preserve_editor_changes=policy == "smart_merge",
                )

        if pending_adjudication:
            max_workers = canonical_adjudication_max_concurrent()
            llm_results = run_callables_parallel(
                [
                    lambda p=item.prepared: run_location_adjudication_llm(p)
                    for item in pending_adjudication
                ],
                max_workers=max_workers,
            )
            for item, llm_data in zip(pending_adjudication, llm_results, strict=True):
                plan = resolve_location_adjudication_plan(
                    item.plan,
                    prepared=item.prepared,
                    llm_data=llm_data,
                )
                _apply_location_plan_and_mention(
                    session,
                    ctx,
                    location=item.location,
                    bucket=item.bucket,
                    entry=item.entry,
                    plan=plan,
                )

        retired_mentions = 0
        substrates_disposed = 0
        if policy == "smart_merge" and touched_location_ids:
            retired_mentions, retired_location_ids = retire_stale_article_mentions_for_rerun(
                session,
                article_id=int(ctx.article_id),
                touched_location_ids=touched_location_ids,
            )
            if retired_location_ids:
                substrates_disposed = dispose_orphan_substrates_after_retired_mentions(
                    session,
                    project_id=int(ctx.project_id),
                    location_ids=retired_location_ids,
                )
            if retired_mentions or substrates_disposed:
                logger.warning(
                    "Superseded ingest for article_id=%s run_id=%s: %s mention(s) retired, "
                    "%s orphan substrate(s) disposed",
                    ctx.article_id,
                    ctx.run_id,
                    retired_mentions,
                    substrates_disposed,
                )

        removed = retired_mentions
        disposed = substrates_disposed
        if ctx.replace_stats is not None:
            removed = ctx.replace_stats.mentions_cleared
            disposed = ctx.replace_stats.substrates_disposed

        return HandlerPersistResult(
            summary=DomainReconciliationSummary(
                policy=policy,
                domain="places",
                added=added,
                updated=updated,
                skipped=skipped,
                removed=removed,
                preserved=preserved,
                disposed=disposed,
            ),
            retired_mentions=retired_mentions,
            disposed_substrates=substrates_disposed,
        )


register_persist_handler(LocationPersistHandler())
