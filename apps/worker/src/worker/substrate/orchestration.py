"""Persist successful Agate graph outputs into shared substrate_* tables."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backfield_stylebook.db_output_settings import (
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
from worker.substrate.entities.registry import (
    DomainReconciliationSummary,
    PersistContext,
    PlacesReconciliationSummary,
    get_persist_handler,
)

logger = logging.getLogger(__name__)

__all__ = [
    "persist_from_consolidated",
    "_find_mention_span",
    "DomainReconciliationSummary",
    "PlacesReconciliationSummary",
]


@dataclass(frozen=True)
class PersistResult:
    article_id: int
    retired_mentions: int
    disposed_substrates: int
    replace_stats: ArticleGeographyReplaceStats | None
    reconciliation_summary: DomainReconciliationSummary

    def __iter__(self):
        yield self.article_id
        yield self.retired_mentions
        yield self.disposed_substrates
        yield self.replace_stats


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

    handler = get_persist_handler("places")
    if handler is None:
        raise RuntimeError("Location persist handler is not registered")

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
    handler_result = handler.persist(session, ctx)

    return PersistResult(
        article_id=int(article.id),
        retired_mentions=handler_result.retired_mentions,
        disposed_substrates=handler_result.disposed_substrates,
        replace_stats=replace_stats,
        reconciliation_summary=handler_result.summary,
    )
