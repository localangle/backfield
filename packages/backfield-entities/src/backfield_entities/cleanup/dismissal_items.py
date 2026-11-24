"""The dismissals route's item pipeline: set aside (or reopen) one check result at a time.

A cluster check (duplicates) is dismissed one pair at a time, so a dismissal never covers pairs the
finder did not propose. A list check (missing geometry) is dismissed per canonical.
"""

from __future__ import annotations

from typing import Literal

from backfield_db import StylebookCleanupDismissal
from pydantic import BaseModel, Field, JsonValue
from pydantic_core import to_jsonable_python
from sqlmodel import Session

from backfield_entities.activity import (
    EVENT_CLEANUP_KEEP,
    EVENT_CLEANUP_KEEP_SEPARATE,
    EVENT_CLEANUP_REOPEN,
    log_stylebook_activity,
)
from backfield_entities.cleanup.before_state import BEFORE_STATE_SCHEMA_VERSION, row_to_json
from backfield_entities.cleanup.entity_models import cleanup_entity_models_for_singular
from backfield_entities.cleanup.envelope import (
    MAX_ITEM_ID_LENGTH,
    MAX_ITEMS_PER_REQUEST,
    REASON_ALREADY_DISMISSED,
    REASON_INVALID_ITEM,
    REASON_NOT_DISMISSED,
    REASON_NOT_FOUND,
    REASON_SAME_CANONICAL,
    REASON_UNKNOWN_CHECK,
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
from backfield_entities.quality.checks import CleanupCheckDef, cleanup_check_by_id
from backfield_entities.quality.dismissals import (
    canonical_dismissal_key,
    dismiss_canonical_issue,
    dismiss_pair,
    find_dismissal,
    pair_key_for_ids,
)

OPERATION = "dismissal"
ACTIVITY_SOURCE = "cleanup_api"
MAX_REASON_CODE_LENGTH = 100

DismissalAction = Literal["dismiss", "reopen"]


class DismissalApplyItem(BaseModel):
    item_id: str = Field(
        min_length=1,
        max_length=MAX_ITEM_ID_LENGTH,
        description="Your own id for this item; echoed back and stored with the action.",
    )
    action: DismissalAction = Field(
        default="dismiss", description="`dismiss` sets the result aside; `reopen` brings it back."
    )
    check_id: str = Field(min_length=1, description="The check the result came from.")
    left_id: str | None = Field(
        default=None, description="Duplicate checks: one canonical of the pair."
    )
    right_id: str | None = Field(
        default=None, description="Duplicate checks: the other canonical of the pair."
    )
    canonical_id: str | None = Field(
        default=None, description="Checks that list single canonicals: the canonical."
    )
    reason_code: str | None = Field(
        default=None,
        max_length=MAX_REASON_CODE_LENGTH,
        description="Why, as a short code of your choosing. Stored as given.",
    )
    provenance: dict[str, JsonValue] | None = Field(
        default=None, description="Anything you want stored with the action, as given."
    )


class DismissalRequestBody(BaseModel):
    run_id: str = Field(min_length=1)
    dry_run: bool = Field(
        default=True, description="Report what would happen without changing anything."
    )
    items: list[DismissalApplyItem] = Field(min_length=1, max_length=MAX_ITEMS_PER_REQUEST)


class DismissalSummary(BaseModel):
    check_id: str
    entity_type: str
    action: DismissalAction
    canonical_ids: list[str] = Field(description="The canonicals the dismissal covers.")


class DismissalApplyResult(ItemResult):
    summary: DismissalSummary | None = None


class DismissalResponse(BaseModel):
    run_id: str
    dry_run: bool
    counts: ApplyCounts
    items: list[DismissalApplyResult]


class DismissalBeforeState(BaseModel):
    """The dismissal as it was before the change; empty when there was none."""

    schema_version: int = BEFORE_STATE_SCHEMA_VERSION
    existing: dict[str, JsonValue] | None


def _error(item: DismissalApplyItem, reason: str, message: str) -> DismissalApplyResult:
    return DismissalApplyResult(
        item_id=item.item_id, status="error", reason=reason, message=message
    )


def _canonicals_for(check: CleanupCheckDef, item: DismissalApplyItem) -> list[str]:
    """The canonical ids an item names, checked against the kind of check."""
    if check.kind == "cluster":
        left, right = (item.left_id or "").strip(), (item.right_id or "").strip()
        if not left or not right or item.canonical_id:
            raise ItemRefused(
                REASON_INVALID_ITEM,
                "This check needs `left_id` and `right_id`, not `canonical_id`.",
            )
        if left == right:
            raise ItemRefused(REASON_SAME_CANONICAL, "The two canonicals are the same.")
        return sorted([left, right])
    canonical_id = (item.canonical_id or "").strip()
    if not canonical_id or item.left_id or item.right_id:
        raise ItemRefused(
            REASON_INVALID_ITEM, "This check needs `canonical_id`, not `left_id` and `right_id`."
        )
    return [canonical_id]


def _require_canonicals_exist(
    session: Session, check: CleanupCheckDef, *, stylebook_id: int, canonical_ids: list[str]
) -> None:
    models = cleanup_entity_models_for_singular(check.entity_type)
    for canonical_id in canonical_ids:
        row = session.get(models.canonical, canonical_id)
        if row is None or int(row.stylebook_id) != int(stylebook_id):
            raise ItemRefused(
                REASON_NOT_FOUND, f"Canonical {canonical_id} is not in this Stylebook."
            )


def _key_for(check: CleanupCheckDef, canonical_ids: list[str]) -> str:
    if check.kind == "cluster":
        return pair_key_for_ids(canonical_ids[0], canonical_ids[1])
    return canonical_dismissal_key(canonical_ids[0])


def _activity_for(
    session: Session,
    *,
    check: CleanupCheckDef,
    item: DismissalApplyItem,
    canonical_ids: list[str],
    stylebook_id: int,
    run_id: str,
    caller: ActionCaller,
) -> None:
    payload: dict[str, JsonValue] = {
        "check_id": check.id,
        "run_id": run_id,
        "client_item_id": item.item_id,
        "credential_id": caller.credential_id,
        "credential_label": caller.credential_label,
        "reason_code": item.reason_code,
        "provenance": item.provenance,
    }
    if item.action == "reopen":
        event_type = EVENT_CLEANUP_REOPEN
    elif check.kind == "cluster":
        event_type = EVENT_CLEANUP_KEEP_SEPARATE
        payload["member_ids"] = list(canonical_ids)
    else:
        event_type = EVENT_CLEANUP_KEEP
        payload["canonical_id"] = canonical_ids[0]
    log_stylebook_activity(
        session,
        stylebook_id=stylebook_id,
        actor_type="agent",
        source=ACTIVITY_SOURCE,
        event_type=event_type,
        entity_type="check",
        entity_id=check.id,
        related_entity_type=check.entity_type if check.kind == "list" else None,
        related_entity_id=canonical_ids[0] if check.kind == "list" else None,
        payload_json=to_jsonable_python(payload),
    )


def _apply_item(
    session: Session,
    *,
    stylebook_id: int,
    run_id: str,
    item: DismissalApplyItem,
    dry_run: bool,
    caller: ActionCaller,
) -> DismissalApplyResult:
    """Do one item; the driver commits an applied result and rolls back everything else."""
    not_open = run_not_open_refusal(session, stylebook_id=stylebook_id, run_id=run_id)
    if not_open is not None:
        raise not_open
    check = cleanup_check_by_id(item.check_id.strip())
    if check is None:
        raise ItemRefused(REASON_UNKNOWN_CHECK, f"Unknown cleanup check: {item.check_id}")
    canonical_ids = _canonicals_for(check, item)
    key = _key_for(check, canonical_ids)
    summary = DismissalSummary(
        check_id=check.id,
        entity_type=check.entity_type,
        action=item.action,
        canonical_ids=canonical_ids,
    )
    existing = find_dismissal(session, stylebook_id=stylebook_id, check_id=check.id, pair_key=key)
    if item.action == "dismiss" and existing is not None:
        return DismissalApplyResult(
            item_id=item.item_id,
            status="noop",
            reason=REASON_ALREADY_DISMISSED,
            message="This result was already set aside.",
            summary=summary,
        )
    if item.action == "reopen" and existing is None:
        return DismissalApplyResult(
            item_id=item.item_id,
            status="noop",
            reason=REASON_NOT_DISMISSED,
            message="This result is not set aside.",
            summary=summary,
        )
    if item.action == "dismiss":
        _require_canonicals_exist(
            session, check, stylebook_id=stylebook_id, canonical_ids=canonical_ids
        )
    refusal = ceiling_refusal(
        session, run_id=run_id, operation=OPERATION, noun="dismissals and reopenings"
    )
    if refusal is not None:
        raise refusal

    before_state = DismissalBeforeState(
        existing=row_to_json(existing) if existing is not None else None
    )
    _change_dismissal(
        session,
        check=check,
        item=item,
        canonical_ids=canonical_ids,
        existing=existing,
        stylebook_id=stylebook_id,
        run_id=run_id,
    )
    if dry_run:
        return DismissalApplyResult(item_id=item.item_id, status="would_apply", summary=summary)
    _activity_for(
        session,
        check=check,
        item=item,
        canonical_ids=canonical_ids,
        stylebook_id=stylebook_id,
        run_id=run_id,
        caller=caller,
    )
    try:
        action = record_action(
            session,
            run_id=run_id,
            stylebook_id=stylebook_id,
            operation=OPERATION,
            entity_type=check.entity_type,
            canonical_id=canonical_ids[0],
            related_canonical_id=canonical_ids[1] if len(canonical_ids) > 1 else None,
            client_item_id=item.item_id,
            provenance=item.provenance,
            caller=caller,
            request=item,
            result=summary,
            before_state=before_state,
            reindex_queued=False,
        )
    except Exception as exc:
        raise LedgerError from exc
    return DismissalApplyResult(
        item_id=item.item_id, status="applied", action_id=str(action.id), summary=summary
    )


def _change_dismissal(
    session: Session,
    *,
    check: CleanupCheckDef,
    item: DismissalApplyItem,
    canonical_ids: list[str],
    existing: StylebookCleanupDismissal | None,
    stylebook_id: int,
    run_id: str,
) -> None:
    """Insert the dismissal, or delete the stored one when reopening."""
    if item.action == "reopen":
        if existing is not None:
            session.delete(existing)
        return
    reason_code = item.reason_code.strip() if item.reason_code else None
    if check.kind == "cluster":
        dismiss_pair(
            session,
            stylebook_id=stylebook_id,
            check_id=check.id,
            left_id=canonical_ids[0],
            right_id=canonical_ids[1],
            reason_code=reason_code,
            run_id=run_id,
        )
    else:
        dismiss_canonical_issue(
            session,
            stylebook_id=stylebook_id,
            check_id=check.id,
            canonical_id=canonical_ids[0],
            reason_code=reason_code,
            run_id=run_id,
        )
    session.flush()


def apply_dismissal_items(
    session: Session,
    *,
    stylebook_id: int,
    body: DismissalRequestBody,
    caller: ActionCaller,
) -> DismissalResponse:
    """Process every item in order and report each one.

    Raises ``RunNotFoundError`` when the run is not in this Stylebook. Commits per item.
    """
    require_run(session, stylebook_id=stylebook_id, run_id=body.run_id)
    results = process_items(
        session,
        items=body.items,
        operation_noun="dismissal",
        apply_one=lambda item: _apply_item(
            session,
            stylebook_id=stylebook_id,
            run_id=body.run_id,
            item=item,
            dry_run=body.dry_run,
            caller=caller,
        ),
        error_result=_error,
    )
    return DismissalResponse(
        run_id=body.run_id,
        dry_run=body.dry_run,
        counts=count_statuses([r.status for r in results]),
        items=results,
    )
