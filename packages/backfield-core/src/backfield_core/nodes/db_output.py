"""DBOutput node — worker persists; core provides a safe offline stub."""

from __future__ import annotations

import os
from typing import Any

from agate_runtime.output_node import (
    OutputConsolidator,
    OutputParams,
    expand_upstream_merge_for_output_consolidator,
)


def run_db_output(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for _upstream_id, payload in inputs.items():
        if isinstance(payload, dict):
            merged.update(payload)
    merged = expand_upstream_merge_for_output_consolidator(merged)

    cons = OutputConsolidator()
    p = OutputParams.model_validate(params)
    body = cons.run(merged, p.model_dump())

    # The Celery worker registers a different `DBOutput` runner that writes Postgres.
    # In `backfield-core` unit tests (and other non-worker hosts), treat this as a no-op that
    # still returns a successful shape so graphs can execute end-to-end.
    _ = os.environ.get("BACKFIELD_PROJECT_ID")
    return {
        **body,
        "success": True,
        "article_id": None,
        "message": "DBOutput persistence is a no-op outside the Agate worker",
    }
