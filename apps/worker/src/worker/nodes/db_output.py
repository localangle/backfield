"""DBOutput node — persists consolidated upstream state directly to Postgres (worker-local)."""

from __future__ import annotations

import os
from typing import Any

from agate_runtime.output_node import (
    OutputConsolidator,
    OutputParams,
    expand_upstream_merge_for_output_consolidator,
)
from sqlmodel import Session

from worker.substrate_persistence import persist_from_consolidated


def _merge_namespaced_upstream_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge upstream node outputs keyed by upstream node id."""

    merged: dict[str, Any] = {}
    for _upstream_id, payload in inputs.items():
        if isinstance(payload, dict):
            merged.update(payload)
    return merged


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

    merged = _merge_namespaced_upstream_inputs(inputs)
    merged = expand_upstream_merge_for_output_consolidator(merged)
    cons = OutputConsolidator()
    p = OutputParams.model_validate(params)
    body = cons.run(merged, p.model_dump())

    engine_url = os.getenv("BACKFIELD_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not engine_url:
        raise RuntimeError("Missing BACKFIELD_DATABASE_URL / DATABASE_URL for DBOutput persistence")

    from sqlalchemy.engine import make_url
    from sqlmodel import create_engine

    connect_args: dict[str, Any] = {}
    try:
        url = make_url(engine_url)
        if url.get_backend_name() == "sqlite":
            connect_args["check_same_thread"] = False
    except Exception:
        pass

    engine = create_engine(engine_url, connect_args=connect_args)
    with Session(engine) as session:
        article_id = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id=graph_id,
            run_id=run_id,
            consolidated=body,
        )
        session.commit()

    return {
        **body,
        "success": True,
        "article_id": article_id,
        "message": "Persisted flow output to substrate_* tables",
    }
