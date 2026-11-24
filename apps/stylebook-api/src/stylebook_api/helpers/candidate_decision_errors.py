"""Turn candidate decision errors from the shared library into HTTP responses."""

from __future__ import annotations

from backfield_entities.cleanup.decision_ops import (
    CandidateAlreadyLinkedError,
    CandidateCanonicalElsewhereError,
    CandidateCanonicalNotFoundError,
    CandidateDecisionError,
    CandidateNotInQueueError,
)
from fastapi import HTTPException


def candidate_decision_http_error(
    exc: CandidateDecisionError, *, not_in_queue_status: int
) -> HTTPException:
    """Map a decision error to a response.

    ``not_in_queue_status`` is the status for a candidate that is not waiting for a decision: the
    accept routes have always answered 400 and the defer routes 409.
    """
    if isinstance(exc, CandidateAlreadyLinkedError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, CandidateNotInQueueError):
        return HTTPException(status_code=not_in_queue_status, detail=str(exc))
    if isinstance(exc, CandidateCanonicalNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, CandidateCanonicalElsewhereError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))
