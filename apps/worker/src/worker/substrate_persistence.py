"""Persist successful Agate graph outputs into shared substrate_* tables."""

from __future__ import annotations

import logging
from typing import Any

from backfield_stylebook.canonical_link import CANONICAL_LINK_UNLINKED
from backfield_stylebook.canonical_policy import (
    decide_canonical_persist_plan,
    plan_requires_llm_canonical_adjudication,
)
from backfield_stylebook.db_output_settings import (
    DbOutputCanonicalSettings,
    resolve_effective_stylebook_id,
)
from backfield_stylebook.locations import (
    apply_canonical_persist_plan,
    apply_canonical_persist_plan_review_only,
    refresh_aliases_for_linked_location,
)
from sqlmodel import Session

from worker.canonical_adjudication import adjudicate_ambiguous_plan_with_llm
from worker.substrate_article import _sync_images, _upsert_article
from worker.substrate_location import _iter_place_entries, _upsert_location
from worker.substrate_mentions import (
    _upsert_mention_and_occurrence,
    retire_stale_article_mentions_for_rerun,
)
from worker.substrate_span import _find_mention_span

logger = logging.getLogger(__name__)

__all__ = ["persist_from_consolidated", "_find_mention_span"]


def persist_from_consolidated(
    session: Session,
    *,
    project_id: int,
    graph_id: str,
    run_id: str,
    consolidated: dict[str, Any],
    db_output_params: dict[str, Any] | None = None,
) -> tuple[int, int]:
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

    touched_location_ids: set[int] = set()

    for bucket, entry in _iter_place_entries(places):
        loc = _upsert_location(
            session,
            project_id=project_id,
            bucket=bucket,
            entry=entry,
            run_id=run_id,
            graph_id=graph_id,
        )
        if loc is None or article.id is None:
            continue
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
        )

    retired_mentions = 0
    if article.id is not None and touched_location_ids:
        retired_mentions = retire_stale_article_mentions_for_rerun(
            session,
            article_id=int(article.id),
            touched_location_ids=touched_location_ids,
        )
        if retired_mentions:
            logger.warning(
                "Re-run retired %s superseded place link(s) for article_id=%s run_id=%s",
                retired_mentions,
                article.id,
                run_id,
            )

    return int(article.id), retired_mentions
