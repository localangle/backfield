"""Persist successful Agate graph outputs into shared substrate_* tables."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backfield_entities.ingest.db_output_settings import (
    DbOutputCanonicalSettings,
    ReconciliationPolicy,
    resolve_effective_stylebook_id,
)
from sqlmodel import Session

from worker.substrate.content.article import _sync_images, _upsert_article
from worker.substrate.content.geography_reset import (
    ArticleGeographyReplaceStats,
    replace_machine_geography_for_article,
)
from worker.substrate.entities.location.handler import LocationPersistHandler  # noqa: F401
from worker.substrate.entities.location.span import _find_mention_span
from worker.substrate.entities.organization.handler import OrganizationPersistHandler  # noqa: F401
from worker.substrate.entities.person.handler import PersonPersistHandler  # noqa: F401
from worker.substrate.entities.registry import (
    DomainReconciliationSummary,
    PersistContext,
    get_persist_handler,
)

logger = logging.getLogger(__name__)

_HANDLER_DISPATCH_ORDER: tuple[str, ...] = ("places", "people", "organizations")

__all__ = [
    "persist_from_consolidated",
    "_find_mention_span",
    "DomainReconciliationSummary",
]


@dataclass(frozen=True)
class PersistResult:
    article_id: int
    retired_mentions: int
    disposed_substrates: int
    replace_stats: ArticleGeographyReplaceStats | None
    reconciliation_summary: DomainReconciliationSummary
    domain_summaries: tuple[DomainReconciliationSummary, ...] = ()
    consolidated_domain_keys: tuple[str, ...] = ()

    def __iter__(self):
        yield self.article_id
        yield self.retired_mentions
        yield self.disposed_substrates
        yield self.replace_stats


def _active_handler_keys(consolidated: dict[str, Any]) -> tuple[str, ...]:
    active: list[str] = []
    places = consolidated.get("places")
    if isinstance(places, dict):
        active.append("places")
    people = consolidated.get("people")
    if isinstance(people, list):
        active.append("people")
    organizations = consolidated.get("organizations")
    if isinstance(organizations, list):
        active.append("organizations")
    return tuple(key for key in _HANDLER_DISPATCH_ORDER if key in active)


def _has_article_embedding(consolidated: dict[str, Any]) -> bool:
    block = consolidated.get("article_embedding")
    return isinstance(block, dict)


def _has_article_metadata(consolidated: dict[str, Any]) -> bool:
    block = consolidated.get("article_metadata")
    return isinstance(block, dict)


def _has_custom_records(consolidated: dict[str, Any]) -> bool:
    block = consolidated.get("custom_records")
    return isinstance(block, dict) and bool(block)


def _has_persistable_consolidated_content(consolidated: dict[str, Any]) -> bool:
    return (
        bool(_active_handler_keys(consolidated))
        or _has_article_embedding(consolidated)
        or _has_article_metadata(consolidated)
        or _has_custom_records(consolidated)
    )


def _empty_reconciliation_summary(
    policy: ReconciliationPolicy,
) -> DomainReconciliationSummary:
    return DomainReconciliationSummary(policy=policy, domain="article")


def _primary_reconciliation_summary(
    summaries: tuple[DomainReconciliationSummary, ...],
    *,
    policy: ReconciliationPolicy,
) -> DomainReconciliationSummary:
    if not summaries:
        return _empty_reconciliation_summary(policy)
    for summary in summaries:
        if summary.domain == "places":
            return summary
    return summaries[0]


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
    active_keys = _active_handler_keys(consolidated)
    if not _has_persistable_consolidated_content(consolidated):
        raise RuntimeError(
            "DBOutput persistence requires consolidated['places'], consolidated['people'], "
            "consolidated['organizations'], consolidated['article_embedding'], "
            "consolidated['article_metadata'], and/or consolidated['custom_records']"
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
    if settings.stylebook_matching_enabled:
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
    else:
        stylebook_id = None

    replace_stats: ArticleGeographyReplaceStats | None = None
    if "places" in active_keys and policy == "replace" and article.id is not None:
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

    ctx = PersistContext(
        project_id=int(project_id),
        graph_id=graph_id,
        run_id=run_id,
        consolidated=consolidated,
        article_id=int(article.id),
        article_text=article_text,
        settings=settings,
        policy=policy,
        stylebook_id=stylebook_id,
        replace_stats=replace_stats,
    )

    domain_summaries: list[DomainReconciliationSummary] = []
    retired_mentions = 0
    disposed_substrates = 0

    for key in active_keys:
        handler = get_persist_handler(key)
        if handler is None:
            raise RuntimeError(f"{key} persist handler is not registered")
        handler_result = handler.persist(session, ctx)
        summary = handler_result.summary
        if key == "places" and replace_stats is not None:
            summary = DomainReconciliationSummary(
                policy=summary.policy,
                domain=summary.domain,
                added=summary.added,
                updated=summary.updated,
                skipped=summary.skipped,
                removed=replace_stats.mentions_cleared,
                preserved=summary.preserved,
                disposed=replace_stats.substrates_disposed,
            )
        domain_summaries.append(summary)
        retired_mentions += handler_result.retired_mentions
        disposed_substrates += handler_result.disposed_substrates

    summaries_tuple = tuple(domain_summaries)
    return PersistResult(
        article_id=int(article.id),
        retired_mentions=retired_mentions,
        disposed_substrates=disposed_substrates,
        replace_stats=replace_stats,
        reconciliation_summary=_primary_reconciliation_summary(summaries_tuple, policy=policy),
        domain_summaries=summaries_tuple,
        consolidated_domain_keys=active_keys,
    )
