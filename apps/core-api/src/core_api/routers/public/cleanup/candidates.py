"""Candidate queue reads: list, count, kinds, and per-candidate evidence."""

from __future__ import annotations

from datetime import date
from typing import Any

from backfield_entities.cleanup.candidates import (
    CANDIDATES_DEFAULT_LIMIT,
    CANDIDATES_MAX_LIMIT,
    CandidateCounts,
    CandidateEvidence,
    CandidateNotFoundError,
    CandidatePage,
    CandidateStatus,
    CandidateTypes,
    count_candidates,
    get_candidate_evidence,
    list_candidate_kinds,
    list_candidates,
    stylebook_project_ids,
)
from backfield_entities.cleanup.check_reads import QueueScope
from backfield_entities.cleanup.cursor import InvalidCursorError
from backfield_entities.cleanup.entity_models import EntityName, cleanup_entity_models
from backfield_entities.cleanup.evidence import (
    DEFAULT_SNIPPET_CHARS,
    DEFAULT_SNIPPET_LIMIT,
    MAX_SNIPPET_LIMIT,
    SnippetControls,
)
from backfield_entities.cleanup.export import ExportFilters
from fastapi import Depends, HTTPException, Query, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.cleanup.deps import (
    CleanupContext,
    get_cleanup_context,
    require_cleanup_read,
    require_queue_scope_allowed,
)
from core_api.routers.public.cleanup.settings import snippet_max_chars

_SCOPE_QUERY = Query(
    default="project",
    description="`project` is the key's project. `stylebook` covers every project (service keys).",
)
_STATUS_QUERY = Query(default="open", description="`open` or `deferred`.")


def _project_ids(
    session: Session, context: CleanupContext, auth: dict[str, Any], scope: QueueScope
) -> list[int]:
    require_queue_scope_allowed(auth, scope)
    if scope == "project":
        return [int(context.project.id)]
    return stylebook_project_ids(
        session,
        stylebook_id=context.stylebook_id,
        organization_id=int(context.project.organization_id),
    )


def get_cleanup_candidates(
    entity: EntityName,
    auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
    scope: QueueScope = _SCOPE_QUERY,
    queue_status: CandidateStatus = Query(default="open", alias="status"),
    q: str | None = Query(default=None, description="Match the record's name."),
    kind: str | None = Query(default=None, description="Place kind, person type or org type."),
    needs_review: bool | None = Query(default=None),
    mentioned_from: date | None = Query(default=None),
    mentioned_to: date | None = Query(default=None),
    cursor: str | None = Query(default=None, description="`next_cursor` from the previous page."),
    limit: int = Query(default=CANDIDATES_DEFAULT_LIMIT, ge=1, le=CANDIDATES_MAX_LIMIT),
) -> CandidatePage:
    """Candidates still waiting for a link decision, ordered like the Stylebook queue."""
    try:
        return list_candidates(
            session,
            cleanup_entity_models(entity),
            project_ids=_project_ids(session, context, auth, scope),
            queue_scope=scope,
            status=queue_status,
            q=q,
            kind=kind,
            needs_review=needs_review,
            date_filters=ExportFilters(mentioned_from=mentioned_from, mentioned_to=mentioned_to),
            cursor=cursor,
            limit=limit,
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def get_cleanup_candidate_count(
    entity: EntityName,
    auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
    scope: QueueScope = _SCOPE_QUERY,
    queue_status: CandidateStatus = Query(default="open", alias="status"),
    q: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    mentioned_from: date | None = Query(default=None),
    mentioned_to: date | None = Query(default=None),
) -> CandidateCounts:
    """How many candidates are waiting, per project."""
    return count_candidates(
        session,
        cleanup_entity_models(entity),
        project_ids=_project_ids(session, context, auth, scope),
        status=queue_status,
        q=q,
        kind=kind,
        needs_review=needs_review,
        date_filters=ExportFilters(mentioned_from=mentioned_from, mentioned_to=mentioned_to),
    )


def get_cleanup_candidate_types(
    entity: EntityName,
    auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
    scope: QueueScope = _SCOPE_QUERY,
    queue_status: CandidateStatus = Query(default="open", alias="status"),
) -> CandidateTypes:
    """Kinds that can be used to filter the queue."""
    return list_candidate_kinds(
        session,
        cleanup_entity_models(entity),
        project_ids=_project_ids(session, context, auth, scope),
        status=queue_status,
    )


def get_cleanup_candidate_evidence(
    entity: EntityName,
    candidate_id: int,
    auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
    scope: QueueScope = _SCOPE_QUERY,
    snippet_limit: int = Query(default=DEFAULT_SNIPPET_LIMIT, ge=0, le=MAX_SNIPPET_LIMIT),
    snippet_chars: int = Query(default=DEFAULT_SNIPPET_CHARS, ge=0),
) -> CandidateEvidence:
    """Article context and ranked catalog matches for one candidate."""
    controls = SnippetControls(snippet_limit=snippet_limit, snippet_chars=snippet_chars)
    try:
        return get_candidate_evidence(
            session,
            cleanup_entity_models(entity),
            stylebook_id=context.stylebook_id,
            project_ids=_project_ids(session, context, auth, scope),
            candidate_id=candidate_id,
            controls=controls.capped(snippet_max_chars()),
        )
    except CandidateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
