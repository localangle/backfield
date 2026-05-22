"""Clear one-shot replace geography flags on agate_run / agate_processed_item."""

from __future__ import annotations

from backfield_db import AgateProcessedItem, AgateRun
from sqlmodel import Session


def clear_replace_article_geography_flags(
    session: Session,
    *,
    run_id: str,
    processed_item_id: int | None = None,
) -> None:
    """Reset flags after persist or when a run completes without DBOutput."""
    if processed_item_id is not None:
        item = session.get(AgateProcessedItem, int(processed_item_id))
        if item is not None:
            item.replace_article_geography_on_persist = False
            session.add(item)
    run = session.get(AgateRun, str(run_id))
    if run is not None:
        run.replace_article_geography_on_persist = False
        session.add(run)
