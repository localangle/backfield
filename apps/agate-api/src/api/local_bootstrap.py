"""Idempotent local dev seed: General project secrets from env + Starter flow graph.

Invoked from entrypoint when BACKFIELD_LOCAL_BOOTSTRAP=1 (not FastAPI lifespan).
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from backfield_core import STARTER_FLOW_GRAPH_DISPLAY_NAME, starter_geocode_flow_graph_spec
from backfield_db import AgateGraph, AgateProject, AgateProjectSecret
from backfield_db.crypto import encrypt_secret, fernet_from_env
from backfield_db.session import get_engine
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

GENERAL_SLUG = "general"

# Keys mirrored from host/.env into agate_project_secret for the General project.
_BOOTSTRAP_SECRET_KEYS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "PELIAS_API_KEY",
    "GEOCODIO_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "MAPBOX_API_TOKEN",
)


def _sync_secrets(session: Session, project_id: int) -> int:
    f = fernet_from_env()
    if f is None:
        logger.warning(
            "local_bootstrap: MASTER_ENCRYPTION_KEY not set; skipping project secret sync"
        )
        return 0
    now = datetime.now(UTC)
    n = 0
    for key in _BOOTSTRAP_SECRET_KEYS:
        value = os.environ.get(key, "").strip()
        if not value:
            continue
        try:
            enc = encrypt_secret(value)
        except RuntimeError as e:
            logger.warning("local_bootstrap: encrypt failed for %s: %s", key, e)
            continue
        existing = session.exec(
            select(AgateProjectSecret).where(
                AgateProjectSecret.project_id == project_id,
                AgateProjectSecret.key == key,
            )
        ).first()
        if existing:
            existing.value_encrypted = enc
            existing.updated_at = now
            session.add(existing)
        else:
            session.add(
                AgateProjectSecret(
                    project_id=project_id,
                    key=key,
                    value_encrypted=enc,
                    created_at=now,
                    updated_at=now,
                )
            )
        n += 1
    return n


def _ensure_starter_graph(session: Session, project_id: int) -> bool:
    existing = session.exec(
        select(AgateGraph).where(
            AgateGraph.project_id == project_id,
            AgateGraph.name == STARTER_FLOW_GRAPH_DISPLAY_NAME,
        )
    ).first()
    if existing:
        return False
    spec = starter_geocode_flow_graph_spec()
    session.add(
        AgateGraph(
            name=STARTER_FLOW_GRAPH_DISPLAY_NAME,
            spec_json=spec.model_dump_json(),
            project_id=project_id,
        )
    )
    return True


def run_local_bootstrap() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    engine = get_engine()
    with Session(engine) as session:
        project = session.exec(
            select(AgateProject).where(AgateProject.slug == GENERAL_SLUG)
        ).first()
        if project is None or project.id is None:
            logger.warning(
                "local_bootstrap: no project with slug %r (run migrations); skipping",
                GENERAL_SLUG,
            )
            return 0
        pid = int(project.id)
        secret_count = _sync_secrets(session, pid)
        added_graph = _ensure_starter_graph(session, pid)
        session.commit()
        if secret_count:
            logger.info("local_bootstrap: upserted %d project secret(s) for General", secret_count)
        if added_graph:
            logger.info(
                "local_bootstrap: created graph %r for General",
                STARTER_FLOW_GRAPH_DISPLAY_NAME,
            )
        if not secret_count and not added_graph:
            logger.info(
                "local_bootstrap: no env secrets to sync and starter graph already exists"
            )
    return 0


def main() -> int:
    return run_local_bootstrap()


if __name__ == "__main__":
    raise SystemExit(main())
