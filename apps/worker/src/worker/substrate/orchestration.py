"""Persist successful Agate graph outputs into shared substrate_* tables."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backfield_db import SubstrateLocationMention
from backfield_stylebook.canonical_link import CANONICAL_LINK_UNLINKED
from backfield_stylebook.canonical_policy import (
    decide_canonical_persist_plan,
    plan_requires_llm_canonical_adjudication,
)
from backfield_stylebook.db_output_settings import (
    DbOutputCanonicalSettings,
    ReconciliationPolicy,
    resolve_effective_stylebook_id,
)
from backfield_stylebook.locations import (
    apply_canonical_persist_plan,
    apply_canonical_persist_plan_review_only,
    refresh_aliases_for_linked_location,
)
from sqlmodel import Session, col, select

from worker.canonical_adjudication import adjudicate_ambiguous_plan_with_llm
from worker.substrate_article import _sync_images, _upsert_article
from worker.substrate_article_geography_reset import (
    ArticleGeographyReplaceStats,
    replace_machine_geography_for_article,
)
from worker.substrate_location import _iter_place_entries, _upsert_location
from worker.substrate_mentions import (
    _upsert_mention_and_occurrence,
    dispose_orphan_substrates_after_retired_mentions,
    retire_stale_article_mentions_for_rerun,
)
from worker.substrate_span import _find_mention_span

logger = logging.getLogger(__name__)

__all__ = ["persist_from_consolidated", "_find_mention_span"]


@dataclass(frozen=True)
class PlacesReconciliationSummary:
    policy: ReconciliationPolicy
    domain: str = "places"
    added: int = 0
    updated: int = 0
    skipped: int = 0
    removed: int = 0
    preserved: int = 0
    disposed: int = 0

    def as_dict(self) -> dict[str, int | str]:
        return {
            "domain": self.domain,
            "policy": self.policy,
            "added": self.added,
            "updated": self.updated,
            "skipped": self.skipped,
            "removed": self.removed,
            "preserved": self.preserved,
            "disposed": self.disposed,
        }


@dataclass(frozen=True)
class PersistResult:
    article_id: int
    retired_mentions: int
    disposed_substrates: int
    replace_stats: ArticleGeographyReplaceStats | None
    reconciliation_summary: PlacesReconciliationSummary

    def __iter__(self):
        yield self.article_id
        yield self.retired_mentions
        yield self.disposed_substrates
        yield self.replace_stats


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


def persist_from_consolidated(
    session: Session,
    *,
    project_id: int,
    graph_id: str,
    run_id: str,
    consolidated: dict[str, Any],
    db_output_params: dict[str, Any] | None = None,
    replace_machine_geography: bool = False,
) -> PersistResult:
    places = consolidated.get("places")
    if not isinstance(places, dict):
        raise RuntimeError(
            "DBOutput persistence requires consolidated['places'] (GeocodeAgent output)"
        )

    article = _upsert_article(
        session,
        project_id=project_id,
        consolidated=consolidated,
        run_id=run_id,
    )
    _sync_images(session, article_id=int(article.id), consolidated=consolidated)

    article_text = str(consolidated.get("text") or "")
    settings = DbOutputCanonicalSettings.from_node_params(db_output_params)
    policy: ReconciliationPolicy = settings.reconciliation_policy
    if replace_machine_geography and not (
        isinstance(db_output_params, dict) and "reconciliation_policy" in db_output_params
    ):
        # Compatibility for queued runs created before the policy moved onto DBOutput.
        policy = "replace"
    try:
        stylebook_id = resolve_effective_stylebook_id(
            session,
            project_id=project_id,
            stylebook_id_override=settings.stylebook_id,
        )
    except LookupError:
        stylebook_id = None
    except ValueError as exc:
        raise RuntimeError(f"DBOutput stylebook resolution failed: {exc}") from exc

    replace_stats: ArticleGeographyReplaceStats | None = None
    if policy == "replace" and article.id is not None:
        replace_stats = replace_machine_geography_for_article(
            session,
            project_id=int(project_id),
            article_id=int(article.id),
            stylebook_id=stylebook_id,
        )
        if replace_stats.mentions_cleared or replace_stats.substrates_disposed:
            logger.warning(
                "Replaced machine geography for article_id=%s before persist: "
                "%s mention(s) cleared, %s orphan substrate(s) disposed",
                article.id,
                replace_stats.mentions_cleared,
                replace_stats.substrates_disposed,
            )

    touched_location_ids: set[int] = set()
    added = 0
    updated = 0
    skipped = 0
    preserved = 0

    for bucket, entry in _iter_place_entries(places):
        upserted = _upsert_location(
            session,
            project_id=project_id,
            bucket=bucket,
            entry=entry,
            run_id=run_id,
            graph_id=graph_id,
            update_existing=policy != "add_only",
        )
        if upserted is None or article.id is None:
            continue
        loc = upserted.location
        active_mention = _active_mention_for_article_location(
            session,
            article_id=int(article.id),
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
        if stylebook_id is not None and loc.stylebook_location_canonical_id is not None:
            refresh_aliases_for_linked_location(
                session,
                stylebook_id=stylebook_id,
                location=loc,
                provenance="substrate_ingest",
            )
        elif stylebook_id is not None:
            plan = decide_canonical_persist_plan(
                session,
                stylebook_id=stylebook_id,
                places_bucket=bucket,
                location=loc,
                entry=entry,
            )
            if (
                settings.canonicalization_mode == "ai_assisted"
                and plan_requires_llm_canonical_adjudication(plan, loc)
            ):
                adj_model = (settings.adjudication_model or "").strip() or "gpt-5-nano"
                plan = adjudicate_ambiguous_plan_with_llm(
                    session,
                    plan=plan,
                    location=loc,
                    stylebook_id=stylebook_id,
                    model=adj_model,
                    model_config_id=settings.adjudication_ai_model_config_id,
                )
            if settings.auto_apply_canonicalization:
                apply_canonical_persist_plan(
                    session,
                    stylebook_id=stylebook_id,
                    location=loc,
                    plan=plan,
                    places_bucket=bucket,
                    provenance="substrate_ingest",
                    auto_apply_canonicalization=True,
                )
            else:
                apply_canonical_persist_plan_review_only(
                    session,
                    stylebook_id=stylebook_id,
                    location=loc,
                    plan=plan,
                    places_bucket=bucket,
                )
        elif loc.stylebook_location_canonical_id is None:
            loc.canonical_link_status = CANONICAL_LINK_UNLINKED
            session.add(loc)
        _upsert_mention_and_occurrence(
            session,
            article_id=int(article.id),
            location_id=int(loc.id),
            article_text=article_text,
            entry=entry,
            run_id=run_id,
            graph_id=graph_id,
            bucket=bucket,
            preserve_editor_changes=policy == "smart_merge",
        )

    retired_mentions = 0
    substrates_disposed = 0
    if (
        policy == "smart_merge"
        and article.id is not None
        and touched_location_ids
    ):
        retired_mentions, retired_location_ids = retire_stale_article_mentions_for_rerun(
            session,
            article_id=int(article.id),
            touched_location_ids=touched_location_ids,
        )
        if retired_location_ids:
            substrates_disposed = dispose_orphan_substrates_after_retired_mentions(
                session,
                project_id=int(project_id),
                location_ids=retired_location_ids,
            )
        if retired_mentions or substrates_disposed:
            logger.warning(
                "Superseded ingest for article_id=%s run_id=%s: %s mention(s) retired, "
                "%s orphan substrate(s) disposed",
                article.id,
                run_id,
                retired_mentions,
                substrates_disposed,
            )

    removed = retired_mentions
    disposed = substrates_disposed
    if replace_stats is not None:
        removed = replace_stats.mentions_cleared
        disposed = replace_stats.substrates_disposed
    summary = PlacesReconciliationSummary(
        policy=policy,
        added=added,
        updated=updated,
        skipped=skipped,
        removed=removed,
        preserved=preserved,
        disposed=disposed,
    )
    return PersistResult(
        article_id=int(article.id),
        retired_mentions=retired_mentions,
        disposed_substrates=substrates_disposed,
        replace_stats=replace_stats,
        reconciliation_summary=summary,
    )
