"""Persist domain handler registry for substrate orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from backfield_entities.ingest.db_output_settings import (
    DbOutputCanonicalSettings,
    ReconciliationPolicy,
)
from sqlmodel import Session

from worker.substrate.content.geography_reset import ArticleGeographyReplaceStats


@dataclass(frozen=True)
class DomainReconciliationSummary:
    policy: ReconciliationPolicy
    domain: str
    added: int = 0
    updated: int = 0
    skipped: int = 0
    removed: int = 0
    preserved: int = 0
    disposed: int = 0

    def as_dict(self) -> dict[str, int | str]:
        return {
            "domain": self.domain,
            "policy": self.policy,
            "added": self.added,
            "updated": self.updated,
            "skipped": self.skipped,
            "removed": self.removed,
            "preserved": self.preserved,
            "disposed": self.disposed,
        }


@dataclass(frozen=True)
class PersistContext:
    project_id: int
    graph_id: str
    run_id: str
    consolidated: dict[str, Any]
    article_id: int
    article_text: str
    settings: DbOutputCanonicalSettings
    policy: ReconciliationPolicy
    stylebook_id: int | None
    replace_stats: ArticleGeographyReplaceStats | None


@dataclass(frozen=True)
class HandlerPersistResult:
    summary: DomainReconciliationSummary
    retired_mentions: int
    disposed_substrates: int


class PersistDomainHandler(Protocol):
    consolidated_key: str

    def persist(self, session: Session, ctx: PersistContext) -> HandlerPersistResult: ...


_HANDLERS: dict[str, PersistDomainHandler] = {}


def register_persist_handler(handler: PersistDomainHandler) -> None:
    _HANDLERS[handler.consolidated_key] = handler


def get_persist_handler(consolidated_key: str) -> PersistDomainHandler | None:
    return _HANDLERS.get(consolidated_key)


def registered_consolidated_keys() -> tuple[str, ...]:
    return tuple(_HANDLERS.keys())
