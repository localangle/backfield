"""Evidence and comparison reads: what a tool needs to judge a canonical or a pair."""

from __future__ import annotations

from backfield_entities.cleanup.entity_models import EntityName, cleanup_entity_models
from backfield_entities.cleanup.evidence import (
    DEFAULT_SNIPPET_CHARS,
    DEFAULT_SNIPPET_LIMIT,
    EVIDENCE_BATCH_MAX,
    MAX_SNIPPET_LIMIT,
    BatchEvidence,
    CanonicalEvidence,
    PairComparison,
    SnippetControls,
    compare_canonicals,
    get_batch_evidence,
    get_canonical_evidence,
)
from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.cleanup.deps import (
    CleanupContext,
    get_cleanup_context,
    require_cleanup_read,
)
from core_api.routers.public.cleanup.settings import snippet_max_chars

_SNIPPET_LIMIT_QUERY = Query(
    default=DEFAULT_SNIPPET_LIMIT,
    ge=0,
    le=MAX_SNIPPET_LIMIT,
    description="Most snippets to return per canonical; 0 returns none.",
)
_SNIPPET_CHARS_QUERY = Query(
    default=DEFAULT_SNIPPET_CHARS,
    ge=0,
    description="Longest snippet in characters. The instance may cap this lower.",
)


class BatchEvidenceRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=EVIDENCE_BATCH_MAX)
    snippet_limit: int = Field(default=DEFAULT_SNIPPET_LIMIT, ge=0, le=MAX_SNIPPET_LIMIT)
    snippet_chars: int = Field(default=DEFAULT_SNIPPET_CHARS, ge=0)


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def get_cleanup_evidence(
    entity: EntityName,
    canonical_id: str,
    _auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
    snippet_limit: int = _SNIPPET_LIMIT_QUERY,
    snippet_chars: int = _SNIPPET_CHARS_QUERY,
) -> CanonicalEvidence:
    """Aliases, metadata, connections, activity, linked records and snippets for one canonical."""
    controls = SnippetControls(snippet_limit=snippet_limit, snippet_chars=snippet_chars)
    evidence = get_canonical_evidence(
        session,
        cleanup_entity_models(entity),
        stylebook_id=context.stylebook_id,
        canonical_id=canonical_id,
        controls=controls.capped(snippet_max_chars()),
    )
    if evidence is None:
        raise _not_found("Canonical")
    return evidence


def post_cleanup_evidence(
    entity: EntityName,
    body: BatchEvidenceRequest,
    _auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
) -> BatchEvidence:
    """Evidence for several canonicals at once. A POST only because of the id list; read-only."""
    controls = SnippetControls(snippet_limit=body.snippet_limit, snippet_chars=body.snippet_chars)
    return get_batch_evidence(
        session,
        cleanup_entity_models(entity),
        stylebook_id=context.stylebook_id,
        canonical_ids=body.ids,
        controls=controls.capped(snippet_max_chars()),
    )


def get_cleanup_compare(
    entity: EntityName,
    canonical_id: str,
    other_id: str,
    _auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
    snippet_limit: int = _SNIPPET_LIMIT_QUERY,
    snippet_chars: int = _SNIPPET_CHARS_QUERY,
) -> PairComparison:
    """Evidence for any pair of canonicals, including pairs no check surfaced."""
    if canonical_id == other_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Choose two different canonicals."
        )
    controls = SnippetControls(snippet_limit=snippet_limit, snippet_chars=snippet_chars)
    comparison = compare_canonicals(
        session,
        cleanup_entity_models(entity),
        stylebook_id=context.stylebook_id,
        left_id=canonical_id,
        right_id=other_id,
        controls=controls.capped(snippet_max_chars()),
    )
    if comparison is None:
        raise _not_found("Canonical")
    return comparison
