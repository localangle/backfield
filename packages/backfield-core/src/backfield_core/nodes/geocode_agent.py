"""GeocodeAgent — LangGraph + LLM geocoding (vendored runtime)."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from backfield_agate.context import AgateEnvContext
from backfield_agate.runners import run_geocode_agent_runtime

logger = logging.getLogger(__name__)


def _build_geocode_cache_resolve(
    project_id: int,
    stylebook_id: int,
) -> Callable[[str, str, dict[str, Any]], dict[str, Any] | None]:
    """Return a sync callable used by ``orchestrate_geocode`` via ``asyncio.to_thread``."""

    # Local imports: keep optional DB stack out of module import graph for non-worker callers.
    from backfield_db.session import get_engine
    from backfield_stylebook.geocode_cache_resolve import try_resolve_geocode_cache
    from sqlmodel import Session

    def resolve(
        location_text: str,
        location_type: str,
        _components: dict[str, Any],
    ) -> dict[str, Any] | None:
        with Session(get_engine()) as session:
            return try_resolve_geocode_cache(
                session,
                project_id=project_id,
                stylebook_id=stylebook_id,
                location_text=location_text,
                location_type=location_type,
            )

    return resolve


def run_geocode_agent(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    ctx = AgateEnvContext()
    raw_pid = os.getenv("BACKFIELD_PROJECT_ID")
    raw_sid = params.get("stylebook_id")
    if raw_sid is None:
        raw_sid = params.get("stylebookId")
    use_cache = bool(params.get("useCache"))
    if use_cache and raw_pid and raw_sid is not None and raw_sid != "":
        try:
            pid = int(raw_pid)
            sid = int(raw_sid)
        except (TypeError, ValueError):
            logger.debug(
                "Geocode DB cache skipped: invalid BACKFIELD_PROJECT_ID or stylebook id (%r, %r)",
                raw_pid,
                raw_sid,
            )
        else:
            from backfield_db import Stylebook
            from backfield_db.session import get_engine
            from sqlmodel import Session

            with Session(get_engine()) as session:
                sb = session.get(Stylebook, sid)
            if sb is None:
                raise ValueError(
                    "This flow uses a catalog that no longer exists. "
                    "Open the Geocode step and choose a catalog that is still available."
                )
            ctx.metadata["cache_resolve"] = _build_geocode_cache_resolve(pid, sid)
    return run_geocode_agent_runtime(params, inputs, ctx)
