"""DBOutput node — persists consolidated upstream state directly to Postgres (worker-local)."""

from __future__ import annotations

import os
from typing import Any

from backfield_agate.output_node import consolidated_body_from_dboutput
from sqlmodel import Session

from worker.substrate_persistence import persist_from_consolidated


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

    body = consolidated_body_from_dboutput(params, inputs)

    from backfield_db.session import get_engine

    with Session(get_engine()) as session:
        article_id = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id=graph_id,
            run_id=run_id,
            consolidated=body,
            db_output_params=params if isinstance(params, dict) else None,
        )
        session.commit()

    return {
        **body,
        "success": True,
        "article_id": article_id,
        "message": "Persisted flow output to substrate_* tables",
    }
