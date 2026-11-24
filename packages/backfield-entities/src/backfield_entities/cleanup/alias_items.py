"""The aliases route's item pipeline: add a name, bring one back, or suppress one.

Removing an alias suppresses it; the row stays. Every alias this route writes carries one fixed
provenance, which link checks trust like an editor's alias.
"""

from __future__ import annotations

from typing import Literal

from backfield_events import record_canonical_updated
from pydantic import BaseModel, Field, JsonValue
from sqlmodel import Session

from backfield_entities.activity import EVENT_CANONICAL_UPDATED, log_stylebook_activity
from backfield_entities.cleanup.alias_ops import (
    AliasChange,
    add_alias,
    matching_alias_rows,
    suppress_alias_rows,
    touch_canonical,
)
from backfield_entities.cleanup.before_state import BEFORE_STATE_SCHEMA_VERSION, RowJson
from backfield_entities.cleanup.entity_models import CleanupEntityModels
from backfield_entities.cleanup.envelope import (
    MAX_ITEM_ID_LENGTH,
    MAX_ITEMS_PER_REQUEST,
    REASON_ALREADY_PRESENT,
    REASON_ALREADY_SUPPRESSED,
    REASON_GUARD_REFUSED,
    REASON_NOT_FOUND,
    ApplyCounts,
    ItemResult,
    count_statuses,
)
from backfield_entities.cleanup.item_driver import (
    ItemRefused,
    LedgerError,
    ceiling_refusal,
    process_items,
    run_not_open_refusal,
)
from backfield_entities.cleanup.ledger import ActionCaller, record_action
from backfield_entities.cleanup.runs import require_run
from backfield_entities.entities.cleanup_alias_provenance import CLEANUP_API_ALIAS_PROVENANCE
from backfield_entities.text.match_normalize import normalize_match_text

OPERATION = "alias"
ACTIVITY_SOURCE = "cleanup_api"
MAX_ALIAS_LENGTH = 300

AliasAction = Literal["add", "suppress"]


class AliasApplyItem(BaseModel):
    item_id: str = Field(
        min_length=1,
        max_length=MAX_ITEM_ID_LENGTH,
        description="Your own id for this item; echoed back and stored with the action.",
    )
    canonical_id: str = Field(min_length=1)
    action: AliasAction = Field(
        description="`add` adds a name (or brings a suppressed one back); `suppress` removes it."
    )
    alias_text: str = Field(min_length=1, max_length=MAX_ALIAS_LENGTH)
    provenance: dict[str, JsonValue] | None = Field(
        default=None, description="Anything you want stored with the action, as given."
    )


class AliasRequestBody(BaseModel):
    run_id: str = Field(min_length=1)
    dry_run: bool = Field(
        default=True, description="Report what would happen without changing anything."
    )
    items: list[AliasApplyItem] = Field(min_length=1, max_length=MAX_ITEMS_PER_REQUEST)


class AliasSummary(BaseModel):
    canonical_id: str
    canonical_label: str
    action: AliasAction
    alias_text: str
    rows_changed: int = Field(description="Stored name forms that were added, restored or hidden.")


class AliasApplyResult(ItemResult):
    summary: AliasSummary | None = None


class AliasResponse(BaseModel):
    run_id: str
    dry_run: bool
    counts: ApplyCounts
    items: list[AliasApplyResult]


class AliasBeforeState(BaseModel):
    """The alias rows this action changed, as they were; rows it created are listed by id."""

    schema_version: int = BEFORE_STATE_SCHEMA_VERSION
    rows_before: list[RowJson]
    created_alias_ids: list[int]


def _error(item: AliasApplyItem, reason: str, message: str) -> AliasApplyResult:
    return AliasApplyResult(item_id=item.item_id, status="error", reason=reason, message=message)


def _change_aliases(
    session: Session,
    models: CleanupEntityModels,
    *,
    canonical: object,
    item: AliasApplyItem,
) -> AliasChange:
    canonical_id = item.canonical_id
    alias_text = item.alias_text.strip()
    if item.action == "add":
        return add_alias(
            session,
            models,
            canonical_id=canonical_id,
            alias_text=alias_text,
            provenance=CLEANUP_API_ALIAS_PROVENANCE,
        )
    if normalize_match_text(alias_text) == normalize_match_text(getattr(canonical, "label", "")):
        raise ItemRefused(
            REASON_GUARD_REFUSED,
            "That is the record's own name. Change the name with an edit instead.",
        )
    rows = matching_alias_rows(session, models, canonical_id=canonical_id, alias_text=alias_text)
    if not rows:
        raise ItemRefused(REASON_NOT_FOUND, "That name is not an alias of this record.")
    return suppress_alias_rows(rows)


def _apply_item(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    run_id: str,
    item: AliasApplyItem,
    dry_run: bool,
    caller: ActionCaller,
) -> AliasApplyResult:
    """Do one item; the driver commits an applied result and rolls back everything else."""
    not_open = run_not_open_refusal(session, stylebook_id=stylebook_id, run_id=run_id)
    if not_open is not None:
        raise not_open
    canonical = session.get(models.canonical, item.canonical_id)
    if canonical is None or int(canonical.stylebook_id) != int(stylebook_id):
        raise ItemRefused(
            REASON_NOT_FOUND, f"Canonical {item.canonical_id} is not in this Stylebook."
        )
    refusal = ceiling_refusal(session, run_id=run_id, operation=OPERATION, noun="alias changes")
    if refusal is not None:
        raise refusal

    change = _change_aliases(session, models, canonical=canonical, item=item)
    summary = AliasSummary(
        canonical_id=item.canonical_id,
        canonical_label=str(canonical.label),
        action=item.action,
        alias_text=item.alias_text.strip(),
        rows_changed=change.rows_changed,
    )
    if not change.changed:
        reason = REASON_ALREADY_PRESENT if item.action == "add" else REASON_ALREADY_SUPPRESSED
        message = (
            "That name is already an alias."
            if item.action == "add"
            else "That alias is already suppressed."
        )
        return AliasApplyResult(
            item_id=item.item_id, status="noop", reason=reason, message=message, summary=summary
        )
    if dry_run:
        return AliasApplyResult(item_id=item.item_id, status="would_apply", summary=summary)

    touch_canonical(canonical)
    _record_activity(session, models, canonical, item, run_id, stylebook_id, caller)
    try:
        action = record_action(
            session,
            run_id=run_id,
            stylebook_id=stylebook_id,
            operation=OPERATION,
            entity_type=models.singular,
            canonical_id=item.canonical_id,
            related_canonical_id=None,
            client_item_id=item.item_id,
            provenance=item.provenance,
            caller=caller,
            request=item,
            result=summary,
            before_state=AliasBeforeState(
                rows_before=change.rows_before, created_alias_ids=change.created_alias_ids
            ),
            reindex_queued=False,
        )
    except Exception as exc:
        raise LedgerError from exc
    return AliasApplyResult(
        item_id=item.item_id, status="applied", action_id=str(action.id), summary=summary
    )


def _record_activity(
    session: Session,
    models: CleanupEntityModels,
    canonical: object,
    item: AliasApplyItem,
    run_id: str,
    stylebook_id: int,
    caller: ActionCaller,
) -> None:
    label = str(getattr(canonical, "label", ""))
    log_stylebook_activity(
        session,
        stylebook_id=stylebook_id,
        actor_type="agent",
        source=ACTIVITY_SOURCE,
        event_type=EVENT_CANONICAL_UPDATED,
        entity_type=models.singular,
        entity_id=item.canonical_id,
        entity_label=label,
        payload_json={
            "alias_action": item.action,
            "alias_text": item.alias_text.strip(),
            "run_id": run_id,
            "client_item_id": item.item_id,
            "credential_id": caller.credential_id,
            "credential_label": caller.credential_label,
            "provenance": item.provenance,
        },
    )
    record_canonical_updated(
        session,
        stylebook_id=stylebook_id,
        entity_type=models.singular,
        canonical_id=item.canonical_id,
        label=label,
    )


def apply_alias_items(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    body: AliasRequestBody,
    caller: ActionCaller,
) -> AliasResponse:
    """Process every item in order and report each one.

    Raises ``RunNotFoundError`` when the run is not in this Stylebook. Commits per item.
    """
    require_run(session, stylebook_id=stylebook_id, run_id=body.run_id)
    results = process_items(
        session,
        items=body.items,
        operation_noun="alias change",
        apply_one=lambda item: _apply_item(
            session,
            models,
            stylebook_id=stylebook_id,
            run_id=body.run_id,
            item=item,
            dry_run=body.dry_run,
            caller=caller,
        ),
        error_result=_error,
    )
    return AliasResponse(
        run_id=body.run_id,
        dry_run=body.dry_run,
        counts=count_statuses([r.status for r in results]),
        items=results,
    )
