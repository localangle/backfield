"""DBOutput node — worker persists; shared package provides a safe offline stub."""

from __future__ import annotations

import os
from typing import Any

from backfield_agate.output_node import consolidated_body_from_dboutput


def run_db_output(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    body = consolidated_body_from_dboutput(params, inputs)

    # The Celery worker registers a different `DBOutput` runner that writes Postgres.
    # In package tests (and other non-worker hosts), treat this as a no-op that still
    # returns a successful shape so graphs can execute end-to-end.
    _ = os.environ.get("BACKFIELD_PROJECT_ID")
    return {
        **body,
        "success": True,
        "article_id": None,
        "message": "DBOutput persistence is a no-op outside the Agate worker",
    }
