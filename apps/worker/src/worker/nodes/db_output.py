"""DBOutput node — persists consolidated upstream state directly to Postgres (worker-local)."""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any

from agate_runtime.output_node import consolidated_body_from_dboutput
from agate_utils.llm import call_llm
from backfield_db.deadlock import is_postgres_deadlock
from backfield_entities.connections.db_output import run_auto_connections_for_db_output
from backfield_entities.ingest.article_embedding import persist_article_embedding_after_db_output
from backfield_entities.ingest.article_metadata import persist_article_metadata_after_db_output
from backfield_entities.ingest.custom_record import persist_custom_records_after_db_output
from backfield_entities.ingest.db_output_settings import DbOutputCanonicalSettings
from backfield_entities.ingest.image_embedding import persist_image_embeddings_after_db_output
from backfield_entities.ingest.semantic_indexing.db_output import (
    build_semantic_indexing_summary,
    sync_semantic_documents_after_db_output,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from worker.flags.replace_geography import clear_replace_article_geography_flags
from worker.semantic_indexing.embed import embed_pending_semantic_documents_for_db_output
from worker.substrate import persist_from_consolidated
from worker.substrate.canonical.llm_call_policy import (
    ADJUDICATION_LLM_MAX_RETRIES,
    ADJUDICATION_LLM_TIMEOUT_S,
)

logger = logging.getLogger(__name__)

_DBOUTPUT_DEADLOCK_MAX_ATTEMPTS = 4


def _persist_db_output_in_session(
    session: Session,
    *,
    body: dict[str, Any],
    params: dict[str, Any],
    project_id: int,
    graph_id: str,
    run_id: str,
    replace_geography: bool,
    processed_item_id: int | None,
    settings: DbOutputCanonicalSettings,
) -> dict[str, Any]:
    persist_result = persist_from_consolidated(
        session,
        project_id=project_id,
        graph_id=graph_id,
        run_id=run_id,
        consolidated=body,
        db_output_params=params,
        replace_machine_geography=replace_geography,
        processed_item_id=processed_item_id,
    )
    article_id = persist_result.article_id
    retired_mentions = persist_result.retired_mentions
    substrates_disposed = persist_result.disposed_substrates
    replace_stats = persist_result.replace_stats
    reconciliation_summary = persist_result.reconciliation_summary.as_dict()
    domain_summaries = [summary.as_dict() for summary in persist_result.domain_summaries] or [
        reconciliation_summary
    ]

    if settings.semantic_indexing_enabled:
        try:
            sync_result = sync_semantic_documents_after_db_output(
                session,
                project_id=project_id,
                article_id=article_id,
                consolidated_domain_keys=persist_result.consolidated_domain_keys,
            )
            embedding_summary = embed_pending_semantic_documents_for_db_output(
                session,
                project_id=project_id,
                article_id=article_id,
                consolidated_domain_keys=persist_result.consolidated_domain_keys,
            )
            semantic_indexing = build_semantic_indexing_summary(
                enabled=True,
                sync_result=sync_result,
                embedding=embedding_summary,
            )
        except Exception as exc:
            semantic_indexing = build_semantic_indexing_summary(
                enabled=True,
                error=str(exc),
            )
    else:
        semantic_indexing = build_semantic_indexing_summary(enabled=False)

    article_embedding_persist = persist_article_embedding_after_db_output(
        session,
        article_id=article_id,
        consolidated=body,
        policy=settings.reconciliation_policy,
    )

    article_metadata_persist = persist_article_metadata_after_db_output(
        session,
        article_id=article_id,
        consolidated=body,
        policy=settings.reconciliation_policy,
        source_run_id=run_id,
    )

    image_embeddings_persist = persist_image_embeddings_after_db_output(
        session,
        article_id=article_id,
        consolidated=body,
        policy=settings.reconciliation_policy,
    )

    custom_records_persist = persist_custom_records_after_db_output(
        session,
        article_id=article_id,
        consolidated=body,
        policy=settings.reconciliation_policy,
        source_run_id=run_id,
    )

    article_text = str(body.get("text") or "")
    connections = run_auto_connections_for_db_output(
        session,
        project_id=project_id,
        article_id=article_id,
        article_text=article_text,
        settings=settings,
        run_id=run_id,
        processed_item_id=processed_item_id,
        call_llm=lambda prompt, **kwargs: call_llm(
            prompt,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            max_retries=ADJUDICATION_LLM_MAX_RETRIES,
            timeout=ADJUDICATION_LLM_TIMEOUT_S,
            **kwargs,
        ),
    )

    clear_replace_article_geography_flags(
        session,
        run_id=run_id,
        processed_item_id=processed_item_id,
    )

    message = "Persisted flow output to substrate_* tables"
    if replace_stats is not None and (
        replace_stats.mentions_cleared or replace_stats.substrates_disposed
    ):
        message += (
            f"; replaced geography ({replace_stats.mentions_cleared} mention(s) cleared, "
            f"{replace_stats.substrates_disposed} prior saved place(s) removed)"
        )
    elif retired_mentions or substrates_disposed:
        parts: list[str] = []
        if retired_mentions:
            parts.append(f"retired {retired_mentions} superseded place link(s)")
        if substrates_disposed:
            parts.append(f"removed {substrates_disposed} orphan saved place(s)")
        message += f"; {', '.join(parts)} from a prior ingest of this story"

    return {
        **body,
        "success": True,
        "article_id": article_id,
        "retired_mention_count": retired_mentions,
        "disposed_substrate_count": substrates_disposed,
        "reconciliation": {
            "policy": reconciliation_summary["policy"],
            "domains": domain_summaries,
        },
        "semantic_indexing": semantic_indexing,
        "article_embedding_persist": article_embedding_persist,
        "article_metadata_persist": article_metadata_persist,
        "image_embeddings_persist": image_embeddings_persist,
        "custom_records_persist": custom_records_persist,
        "connections": connections,
        "message": message,
    }


def run_db_output(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    project_id_raw = os.getenv("BACKFIELD_PROJECT_ID")
    graph_id = os.getenv("BACKFIELD_GRAPH_ID")
    run_id = os.getenv("BACKFIELD_RUN_ID")
    if not project_id_raw or not graph_id or not run_id:
        raise RuntimeError(
            "Missing BACKFIELD_PROJECT_ID / BACKFIELD_GRAPH_ID / BACKFIELD_RUN_ID env vars "
            "(worker should set these around execute_graph)"
        )
    project_id = int(project_id_raw)
    replace_geography = os.getenv("BACKFIELD_REPLACE_ARTICLE_GEOGRAPHY", "").strip() in (
        "1",
        "true",
        "yes",
    )
    item_id_raw = os.getenv("BACKFIELD_PROCESSED_ITEM_ID", "").strip()
    processed_item_id = int(item_id_raw) if item_id_raw.isdigit() else None

    body = consolidated_body_from_dboutput(params, inputs)
    node_params = params if isinstance(params, dict) else None
    settings = DbOutputCanonicalSettings.from_node_params(node_params)
    persist_params = params if isinstance(params, dict) else {}

    from backfield_db.session import get_engine

    last_exc: SQLAlchemyError | None = None
    for attempt in range(_DBOUTPUT_DEADLOCK_MAX_ATTEMPTS):
        try:
            with Session(get_engine()) as session:
                result = _persist_db_output_in_session(
                    session,
                    body=body,
                    params=persist_params,
                    project_id=project_id,
                    graph_id=graph_id,
                    run_id=run_id,
                    replace_geography=replace_geography,
                    processed_item_id=processed_item_id,
                    settings=settings,
                )
                session.commit()
            return result
        except SQLAlchemyError as exc:
            last_exc = exc
            if not is_postgres_deadlock(exc) or attempt >= _DBOUTPUT_DEADLOCK_MAX_ATTEMPTS - 1:
                raise
            delay_s = 0.05 * (2**attempt) + random.uniform(0, 0.05)
            logger.warning(
                "DBOutput deadlock on attempt %s/%s for run_id=%s; retrying in %.2fs",
                attempt + 1,
                _DBOUTPUT_DEADLOCK_MAX_ATTEMPTS,
                run_id,
                delay_s,
            )
            time.sleep(delay_s)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("DBOutput persist failed without an exception")
