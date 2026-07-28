"""POST /public/v1/projects/{project_slug}/runs."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from agate_runtime.run_trigger import trigger_agate_run
from backfield_db import (
    AgateGraph,
    AgateRun,
    BackfieldProject,
    BackfieldPublicIdempotencyRecord,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from core_api.deps import get_session
from core_api.routers.public.deps import get_public_project, require_scope
from core_api.routers.public.runs.helpers import public_run_snapshot
from core_api.routers.public.runs.schemas import PublicRunCreateIn, PublicRunOut
from core_api.run_enqueue import (
    ENQUEUE_STATE_PENDING,
    encode_enqueue_args,
    enqueue_worker_task,
    publish_idempotency_enqueue,
)

router = APIRouter()

IDEMPOTENCY_RETENTION = timedelta(days=7)
IDEMPOTENCY_CLEANUP_BATCH_SIZE = 100
INITIAL_POLL_SECONDS = 2
_OPERATION = "create_run"
_IDEMPOTENCY_KEY_REGEX = r"^[A-Za-z0-9][A-Za-z0-9._~:/=+\-]{0,127}$"
_IDEMPOTENCY_KEY_PATTERN = re.compile(_IDEMPOTENCY_KEY_REGEX)


def _canonical_request_hash(body: PublicRunCreateIn) -> str:
    canonical = json.dumps(
        body.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    if not _IDEMPOTENCY_KEY_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Idempotency-Key must be 1-128 characters and contain only letters, "
                "numbers, or . _ ~ : / = + -."
            ),
        )
    return value


def _is_expired(record: BackfieldPublicIdempotencyRecord, now: datetime) -> bool:
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now


def _find_record(
    session: Session,
    *,
    project_id: int,
    idempotency_key: str,
) -> BackfieldPublicIdempotencyRecord | None:
    return session.exec(
        select(BackfieldPublicIdempotencyRecord).where(
            BackfieldPublicIdempotencyRecord.project_id == project_id,
            BackfieldPublicIdempotencyRecord.operation == _OPERATION,
            BackfieldPublicIdempotencyRecord.idempotency_key == idempotency_key,
        )
    ).first()


def _cleanup_expired_records(session: Session, *, now: datetime) -> int:
    """Delete one bounded expiry-ordered batch and commit it independently."""
    expired_ids = session.exec(
        select(BackfieldPublicIdempotencyRecord.id)
        .where(BackfieldPublicIdempotencyRecord.expires_at <= now)
        .order_by(BackfieldPublicIdempotencyRecord.expires_at)
        .limit(IDEMPOTENCY_CLEANUP_BATCH_SIZE)
    ).all()
    ids = [int(record_id) for record_id in expired_ids if record_id is not None]
    if not ids:
        return 0
    session.exec(
        delete(BackfieldPublicIdempotencyRecord).where(
            col(BackfieldPublicIdempotencyRecord.id).in_(ids)
        )
    )
    session.commit()
    return len(ids)


def _set_run_headers(response: Response, *, project_slug: str, run_id: str) -> None:
    response.headers["Location"] = f"/public/v1/projects/{project_slug}/runs/{run_id}"
    response.headers["Retry-After"] = str(INITIAL_POLL_SECONDS)


def _run_snapshot_for_record(
    session: Session,
    *,
    record: BackfieldPublicIdempotencyRecord,
    graph: AgateGraph,
) -> PublicRunOut:
    if record.run_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "idempotency_request_in_progress",
                "message": "The original request is still being created; retry shortly.",
            },
            headers={"Retry-After": str(INITIAL_POLL_SECONDS)},
        )
    run = session.get(AgateRun, record.run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "idempotency_run_missing",
                "message": "The original run is no longer available.",
            },
        )
    return public_run_snapshot(session, run=run, graph=graph)


def _raise_enqueue_unavailable() -> None:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "reason": "enqueue_unavailable",
            "message": (
                "The run was reserved but could not be queued for execution. "
                "Retry the same Idempotency-Key shortly."
            ),
        },
        headers={"Retry-After": str(INITIAL_POLL_SECONDS)},
    )


def _publish_and_snapshot(
    session: Session,
    *,
    record: BackfieldPublicIdempotencyRecord,
    graph: AgateGraph,
    response: Response,
    project_slug: str,
    replayed: bool,
) -> PublicRunOut:
    outcome = publish_idempotency_enqueue(
        session,
        record,
        enqueue_task=enqueue_worker_task,
    )
    if outcome == "unavailable":
        _raise_enqueue_unavailable()
    snapshot = _run_snapshot_for_record(session, record=record, graph=graph)
    _set_run_headers(response, project_slug=project_slug, run_id=snapshot.run_id)
    if replayed or outcome == "in_progress":
        response.headers["Idempotency-Replayed"] = "true"
    return snapshot


def _replay_or_conflict(
    session: Session,
    *,
    record: BackfieldPublicIdempotencyRecord,
    request_hash: str,
    graph: AgateGraph,
    response: Response,
    project_slug: str,
) -> PublicRunOut:
    if record.request_hash != request_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "idempotency_key_reused",
                "message": "Idempotency-Key was already used with a different request body.",
            },
        )
    return _publish_and_snapshot(
        session,
        record=record,
        graph=graph,
        response=response,
        project_slug=project_slug,
        replayed=True,
    )


def create_public_run(
    body: PublicRunCreateIn,
    response: Response,
    idempotency_key_header: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
        pattern=_IDEMPOTENCY_KEY_REGEX,
    ),
    project: BackfieldProject = Depends(get_public_project),
    _auth: dict[str, Any] = Depends(require_scope("runs:trigger")),
    session: Session = Depends(get_session),
) -> PublicRunOut:
    graph = session.get(AgateGraph, body.graph_id.strip())
    if graph is None or int(graph.project_id) != int(project.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Graph not found")
    if not graph.public_run_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Graph is not enabled for public run trigger.",
        )

    idempotency_key = _validate_idempotency_key(idempotency_key_header)
    request_hash = _canonical_request_hash(body)
    now = datetime.now(UTC)
    project_id = int(project.id)

    _cleanup_expired_records(session, now=now)
    reservation: BackfieldPublicIdempotencyRecord | None = None
    if idempotency_key is not None:
        existing = _find_record(
            session,
            project_id=project_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None and not _is_expired(existing, now):
            return _replay_or_conflict(
                session,
                record=existing,
                request_hash=request_hash,
                graph=graph,
                response=response,
                project_slug=project.slug,
            )
        if existing is not None:
            session.delete(existing)
            session.flush()

        reservation = BackfieldPublicIdempotencyRecord(
            project_id=project_id,
            operation=_OPERATION,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            enqueue_state=ENQUEUE_STATE_PENDING,
            expires_at=now + IDEMPOTENCY_RETENTION,
        )
        session.add(reservation)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            winner = _find_record(
                session,
                project_id=project_id,
                idempotency_key=idempotency_key,
            )
            if winner is None:
                raise
            return _replay_or_conflict(
                session,
                record=winner,
                request_hash=request_hash,
                graph=graph,
                response=response,
                project_slug=project.slug,
            )

    try:
        triggered = trigger_agate_run(
            session,
            graph=graph,
            inputs=body.inputs,  # type: ignore[arg-type]
            replace_article_geography_on_persist=False,
            enqueue=enqueue_worker_task,
            commit=idempotency_key is None,
        )
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        session.rollback()
        raise

    if reservation is not None:
        if triggered.enqueue_task_name is None or triggered.enqueue_args is None:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Run was created without an enqueue descriptor.",
            )
        reservation.run_id = triggered.run.id
        reservation.enqueue_task_name = triggered.enqueue_task_name
        reservation.enqueue_args_json = encode_enqueue_args(triggered.enqueue_args)
        reservation.enqueue_state = ENQUEUE_STATE_PENDING
        session.add(reservation)
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise
        session.refresh(reservation)
        return _publish_and_snapshot(
            session,
            record=reservation,
            graph=graph,
            response=response,
            project_slug=project.slug,
            replayed=False,
        )

    run = triggered.run
    _set_run_headers(response, project_slug=project.slug, run_id=run.id)
    return public_run_snapshot(session, run=run, graph=graph)
