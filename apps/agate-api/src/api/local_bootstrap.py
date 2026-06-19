"""Idempotent local dev seed: General project secrets from env.

Invoked from entrypoint when BACKFIELD_LOCAL_BOOTSTRAP=1 (not FastAPI lifespan).
Does not create Agate graphs; flows are created in the UI or by smoke harnesses.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldProjectSecret,
    BackfieldWorkspace,
)
from backfield_db.crypto import encrypt_secret, fernet_from_env
from backfield_db.session import get_engine
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

GENERAL_SLUG = "general"
DEFAULT_ORG_SLUG = "default"
DEFAULT_WORKSPACE_SLUG = "default"
DEFAULT_WORKSPACE_DISPLAY_NAME = "Default Workspace"

# Keys mirrored from host/.env into backfield_project_secret for the General project.
# Platform geocoding / search / S3 keys are intentionally omitted: they are configured under
# Settings → Integrations (organization secrets) or worker env merge. Seeding them here created
# rows that the Project Integrations UI treated as project-specific overrides.
_BOOTSTRAP_SECRET_KEYS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "AZURE_API_KEY",
    "AZURE_API_BASE",
)


def _ensure_default_workspace_and_general(session: Session) -> None:
    """Idempotent: default workspace under default org; General project uses that workspace."""
    org = session.exec(
        select(BackfieldOrganization).where(BackfieldOrganization.slug == DEFAULT_ORG_SLUG)
    ).first()
    if org is None or org.id is None:
        return
    oid = int(org.id)
    default_sb = ensure_default_stylebook_for_organization(session, oid)
    sb_id = int(default_sb.id)  # type: ignore[arg-type]
    ws = session.exec(
        select(BackfieldWorkspace).where(
            BackfieldWorkspace.organization_id == oid,
            BackfieldWorkspace.slug == DEFAULT_WORKSPACE_SLUG,
        )
    ).first()
    if ws is None:
        ws = BackfieldWorkspace(
            organization_id=oid,
            stylebook_id=sb_id,
            name=DEFAULT_WORKSPACE_DISPLAY_NAME,
            slug=DEFAULT_WORKSPACE_SLUG,
        )
        session.add(ws)
        session.flush()
    else:
        if int(ws.stylebook_id) != sb_id:
            ws.stylebook_id = sb_id
            session.add(ws)

    project = session.exec(
        select(BackfieldProject).where(BackfieldProject.slug == GENERAL_SLUG)
    ).first()
    if project is None or project.id is None or ws.id is None:
        return
    if project.workspace_id is None:
        project.workspace_id = int(ws.id)
        session.add(project)


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
            select(BackfieldProjectSecret).where(
                BackfieldProjectSecret.project_id == project_id,
                BackfieldProjectSecret.key == key,
            )
        ).first()
        if existing:
            existing.value_encrypted = enc
            existing.updated_at = now
            session.add(existing)
        else:
            session.add(
                BackfieldProjectSecret(
                    project_id=project_id,
                    key=key,
                    value_encrypted=enc,
                    created_at=now,
                    updated_at=now,
                )
            )
        n += 1
    return n


def run_local_bootstrap() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    engine = get_engine()
    with Session(engine) as session:
        _ensure_default_workspace_and_general(session)
        project = session.exec(
            select(BackfieldProject).where(BackfieldProject.slug == GENERAL_SLUG)
        ).first()
        if project is None or project.id is None:
            logger.warning(
                "local_bootstrap: no project with slug %r (run migrations); skipping",
                GENERAL_SLUG,
            )
            return 0
        pid = int(project.id)
        secret_count = _sync_secrets(session, pid)
        session.commit()
        if secret_count:
            logger.info("local_bootstrap: upserted %d project secret(s) for General", secret_count)
        else:
            logger.info("local_bootstrap: no env secrets to sync for General")
    return 0


def main() -> int:
    return run_local_bootstrap()


if __name__ == "__main__":
    raise SystemExit(main())
