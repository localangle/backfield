"""Public run status and count helpers."""

from __future__ import annotations

from agate_runtime.s3_batch import graph_spec_json_contains_s3_input
from backfield_db import AgateGraph, AgateProcessedItem, AgateRun
from sqlalchemy import func
from sqlmodel import Session, select


def run_item_counts(
    session: Session,
    *,
    run: AgateRun,
    graph: AgateGraph | None,
) -> tuple[int, int, int, int, int]:
    """Return (total, pending, running, succeeded, failed) for a run."""
    rows = session.exec(
        select(AgateProcessedItem.status, func.count())
        .where(AgateProcessedItem.run_id == run.id)
        .group_by(AgateProcessedItem.status)
    ).all()
    if rows:
        total = pending = running = succeeded = failed = 0
        for status, count in rows:
            n = int(count)
            total += n
            if status == "pending":
                pending += n
            elif status == "running":
                running += n
            elif status == "succeeded":
                succeeded += n
            elif status in ("failed", "timed_out"):
                failed += n
        return total, pending, running, succeeded, failed

    if graph is None:
        return 0, 0, 0, 0, 0
    if graph_spec_json_contains_s3_input(graph.spec_json):
        return 0, 0, 0, 0, 0
    if run.status == "pending":
        return 1, 1, 0, 0, 0
    if run.status == "running":
        return 1, 0, 1, 0, 0
    if run.status == "succeeded":
        return 1, 0, 0, 1, 0
    if run.status == "failed":
        return 1, 0, 0, 0, 1
    return 0, 0, 0, 0, 0
