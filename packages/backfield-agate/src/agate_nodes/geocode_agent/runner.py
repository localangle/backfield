"""GeocodeAgent runner for the Backfield executor."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from agate_runtime.context import AgateEnvContext
from agate_runtime.runners import run_geocode_agent_runtime

logger = logging.getLogger(__name__)


def _build_geocode_cache_bundle(
    project_id: int,
    stylebook_id: int | None,
) -> dict[str, Callable[..., Any]]:
    """Return callables for strict resolve + adjudication candidates + canonical materialization."""

    from backfield_db.session import get_engine
    from backfield_stylebook.geocode_cache_resolve import (
        build_geocode_cache_adjudication_candidates,
        materialize_canonical_match_dict,
        resolve_geocode_cache_strict_with_outcome,
    )
    from sqlmodel import Session

    def strict_resolve_with_outcome(
        location_text: str,
        location_type: str,
        components: dict[str, Any],
    ) -> dict[str, Any]:
        comps = components if isinstance(components, dict) else None
        with Session(get_engine()) as session:
            outcome = resolve_geocode_cache_strict_with_outcome(
                session,
                project_id=project_id,
                stylebook_id=stylebook_id,
                location_text=location_text,
                location_type=location_type,
                components=comps,
            )
            return {
                "match_dict": outcome.match_dict,
                "ambiguous_tier1": outcome.ambiguous_tier1,
                "tier2_sanity_failed": outcome.tier2_sanity_failed,
            }

    def adjudication_candidates(
        location_text: str,
        location_type: str,
        components: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if stylebook_id is None:
            return []
        comps = components if isinstance(components, dict) else None
        with Session(get_engine()) as session:
            return build_geocode_cache_adjudication_candidates(
                session,
                stylebook_id=stylebook_id,
                location_text=location_text,
                location_type=location_type,
                components=comps,
            )

    def materialize_canonical(
        canonical_id: str,
        substrate_location_type: str | None = None,
        location_text: str | None = None,
        components: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if stylebook_id is None:
            return None
        with Session(get_engine()) as session:
            return materialize_canonical_match_dict(
                session,
                stylebook_id=stylebook_id,
                canonical_id=str(canonical_id).strip(),
                substrate_location_type=substrate_location_type,
                location_text=location_text,
                components=components if isinstance(components, dict) else None,
            )

    return {
        "strict_resolve_with_outcome": strict_resolve_with_outcome,
        "adjudication_candidates": adjudication_candidates,
        "materialize_canonical": materialize_canonical,
    }


def run_geocode_agent(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    ctx = AgateEnvContext()
    raw_pid = os.getenv("BACKFIELD_PROJECT_ID")
    raw_sid = params.get("stylebook_id")
    if raw_sid is None:
        raw_sid = params.get("stylebookId")
    use_cache = bool(params.get("useCache"))
    if use_cache and raw_pid:
        try:
            pid = int(raw_pid)
            sid = None if raw_sid is None or raw_sid == "" else int(raw_sid)
        except (TypeError, ValueError):
            logger.debug(
                "Geocode DB cache skipped: invalid BACKFIELD_PROJECT_ID or stylebook id (%r, %r)",
                raw_pid,
                raw_sid,
            )
        else:
            if sid is not None:
                from backfield_db import Stylebook
                from backfield_db.session import get_engine
                from sqlmodel import Session

                with Session(get_engine()) as session:
                    sb = session.get(Stylebook, sid)
                if sb is None:
                    raise ValueError(
                        "This flow uses a Stylebook that no longer exists. "
                        "Open the Geocode step and choose a Stylebook that is still available."
                    )
            ctx.metadata["geocode_cache_bundle"] = _build_geocode_cache_bundle(pid, sid)
    return run_geocode_agent_runtime(params, inputs, ctx)
