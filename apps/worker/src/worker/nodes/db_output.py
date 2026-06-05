"""DBOutput node — persists consolidated upstream state directly to Postgres (worker-local)."""

from __future__ import annotations

import os
from typing import Any

from agate_runtime.output_node import consolidated_body_from_dboutput
from backfield_entities.ingest.db_output_settings import DbOutputCanonicalSettings
from backfield_entities.ingest.semantic_indexing.db_output import (
    build_semantic_indexing_summary,
    sync_semantic_documents_after_db_output,
)
from sqlmodel import Session

from worker.flags.replace_geography import clear_replace_article_geography_flags
from worker.semantic_indexing.embed import embed_pending_semantic_documents_for_db_output
from worker.substrate import persist_from_consolidated


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

    from backfield_db.session import get_engine

    with Session(get_engine()) as session:
        persist_result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id=graph_id,
            run_id=run_id,
            consolidated=body,
            db_output_params=params if isinstance(params, dict) else None,
            replace_machine_geography=replace_geography,
        )
        article_id = persist_result.article_id
        retired_mentions = persist_result.retired_mentions
        substrates_disposed = persist_result.disposed_substrates
        replace_stats = persist_result.replace_stats
        reconciliation_summary = persist_result.reconciliation_summary.as_dict()
        domain_summaries = [
            summary.as_dict() for summary in persist_result.domain_summaries
        ] or [reconciliation_summary]

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

        clear_replace_article_geography_flags(
            session,
            run_id=run_id,
            processed_item_id=processed_item_id,
        )
        session.commit()

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
        "message": message,
    }
