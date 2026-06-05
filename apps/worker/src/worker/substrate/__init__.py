"""Substrate ingest: content carriers, entity persistence, canonical adjudication."""

from worker.substrate.entities.location.span import _find_mention_span
from worker.substrate.orchestration import (
    DomainReconciliationSummary,
    PersistResult,
    persist_from_consolidated,
)

__all__ = [
    "DomainReconciliationSummary",
    "PersistResult",
    "_find_mention_span",
    "persist_from_consolidated",
]
