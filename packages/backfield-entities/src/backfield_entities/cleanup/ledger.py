"""Write one ledger row for an applied cleanup item, in the caller's transaction."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db import StylebookCleanupAction
from pydantic import BaseModel, JsonValue
from sqlmodel import Session


@dataclass(frozen=True)
class ActionCaller:
    """The key (or trusted service token) behind an apply, recorded on every ledger row."""

    credential_id: int | None
    credential_label: str | None


def record_action(
    session: Session,
    *,
    run_id: str,
    stylebook_id: int,
    operation: str,
    entity_type: str,
    canonical_id: str,
    related_canonical_id: str | None,
    client_item_id: str,
    provenance: dict[str, JsonValue] | None,
    caller: ActionCaller,
    request: BaseModel,
    result: BaseModel,
    before_state: BaseModel,
    reindex_queued: bool,
) -> StylebookCleanupAction:
    """Add and flush the row. A failure here must fail the item, so callers never swallow it."""
    action = StylebookCleanupAction(
        run_id=run_id,
        stylebook_id=stylebook_id,
        operation=operation,
        entity_type=entity_type,
        canonical_id=canonical_id,
        related_canonical_id=related_canonical_id,
        client_item_id=client_item_id,
        provenance_json=provenance,
        credential_id=caller.credential_id,
        credential_label=caller.credential_label,
        request_json=request.model_dump(mode="json"),
        result_json=result.model_dump(mode="json"),
        before_state_json=before_state.model_dump(mode="json"),
        reindex_queued=reindex_queued,
    )
    session.add(action)
    session.flush()
    return action
