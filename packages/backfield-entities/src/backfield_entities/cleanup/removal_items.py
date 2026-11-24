"""The retirements and deletions routes' item pipelines.

A retirement makes a record inactive (and can bring it back). A deletion removes it for good. Both
deal with the project records still linked to it through `mention_disposition`: `refuse` (the
default) stops if any are linked, `requeue` returns them to the review queue, `waive` marks them as
not needing a record.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, JsonValue
from sqlmodel import Session

from backfield_entities.cleanup.apply_merge import ReindexEntity
from backfield_entities.cleanup.before_state import (
    BEFORE_STATE_SCHEMA_VERSION,
    RowJson,
    SourceBeforeState,
    capture_canonical_before_state,
)
from backfield_entities.cleanup.entity_models import CleanupEntityModels
from backfield_entities.cleanup.envelope import (
    MAX_ITEM_ID_LENGTH,
    MAX_ITEMS_PER_REQUEST,
    REASON_ALREADY_ACTIVE,
    REASON_ALREADY_DELETED,
    REASON_ALREADY_INACTIVE,
    REASON_LINKED_RECORDS_PRESENT,
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
from backfield_entities.cleanup.redirects import was_deleted_by_cleanup_run
from backfield_entities.cleanup.removal_ops import (
    DELETED_RELEASE_REASON,
    RETIRED_RELEASE_REASON,
    STATUS_INACTIVE,
    MentionDisposition,
    ReleaseDisposition,
    RemovalActivity,
    RemovalOutcome,
    delete_canonical,
    linked_records_for_canonical,
    reinstate_canonical,
    retire_canonical,
)
from backfield_entities.cleanup.runs import require_run

RETIREMENT = "retirement"
DELETION = "deletion"
ACTIVITY_SOURCE = "cleanup_api"
MAX_REASON_CODE_LENGTH = 100

RetirementAction = Literal["retire", "reinstate"]


class LinkedRecordRef(BaseModel):
    project_id: int
    record_id: int


class _RemovalItemFields(BaseModel):
    item_id: str = Field(
        min_length=1,
        max_length=MAX_ITEM_ID_LENGTH,
        description="Your own id for this item; echoed back and stored with the action.",
    )
    canonical_id: str = Field(min_length=1)
    mention_disposition: MentionDisposition = Field(
        default="refuse",
        description=(
            "What to do with records still linked to it. `refuse` stops if any are linked; "
            "`requeue` returns them to the review queue; `waive` marks them as not needing a "
            "record."
        ),
    )
    mention_reason_code: str | None = Field(
        default=None,
        max_length=MAX_REASON_CODE_LENGTH,
        description="Why, as a short code of your choosing. Stored on each released record.",
    )
    provenance: dict[str, JsonValue] | None = Field(
        default=None, description="Anything you want stored with the action, as given."
    )


class RetirementApplyItem(_RemovalItemFields):
    action: RetirementAction = Field(
        default="retire", description="`retire` makes it inactive; `reinstate` makes it active."
    )


class DeletionApplyItem(_RemovalItemFields):
    pass


class RetirementRequestBody(BaseModel):
    run_id: str = Field(min_length=1)
    dry_run: bool = Field(
        default=True, description="Report what would happen without changing anything."
    )
    items: list[RetirementApplyItem] = Field(min_length=1, max_length=MAX_ITEMS_PER_REQUEST)


class DeletionRequestBody(BaseModel):
    run_id: str = Field(min_length=1)
    dry_run: bool = Field(
        default=True, description="Report what would happen without changing anything."
    )
    items: list[DeletionApplyItem] = Field(min_length=1, max_length=MAX_ITEMS_PER_REQUEST)


class RemovalSummary(BaseModel):
    canonical_id: str
    canonical_label: str
    action: Literal["retire", "reinstate", "delete"]
    mention_disposition: MentionDisposition
    released_record_count: int = Field(
        description="Linked project records that were released from the canonical."
    )
    released_records: list[LinkedRecordRef]
    connections_closed: int


class RemovalApplyResult(ItemResult):
    summary: RemovalSummary | None = None


class RemovalResponse(BaseModel):
    run_id: str
    dry_run: bool
    counts: ApplyCounts
    items: list[RemovalApplyResult]


class RemovalBeforeState(BaseModel):
    """The canonical with its aliases, metadata and connections, and the records released."""

    schema_version: int = BEFORE_STATE_SCHEMA_VERSION
    operation: str
    entity_type: str
    canonical: SourceBeforeState
    released_records: list[RowJson]


def _error(item: _RemovalItemFields, reason: str, message: str) -> RemovalApplyResult:
    return RemovalApplyResult(item_id=item.item_id, status="error", reason=reason, message=message)


def _release_disposition(item: _RemovalItemFields, linked_count: int) -> ReleaseDisposition:
    """The release to carry out, or a refusal when `refuse` meets linked records."""
    if item.mention_disposition == "refuse":
        if linked_count:
            raise ItemRefused(
                REASON_LINKED_RECORDS_PRESENT,
                f"{linked_count} linked record(s) still point at this one. Use "
                "`mention_disposition` `requeue` or `waive` to release them first.",
            )
        return "requeue"
    return item.mention_disposition


def _reason_code(item: _RemovalItemFields, default: str) -> str:
    return item.mention_reason_code.strip() if item.mention_reason_code else default


def _summary(
    action: Literal["retire", "reinstate", "delete"],
    item: _RemovalItemFields,
    outcome: RemovalOutcome,
) -> RemovalSummary:
    return RemovalSummary(
        canonical_id=outcome.canonical_id,
        canonical_label=outcome.label,
        action=action,
        mention_disposition=item.mention_disposition,
        released_record_count=len(outcome.released_records),
        released_records=[
            LinkedRecordRef(project_id=project_id, record_id=record_id)
            for project_id, record_id in outcome.released_records
        ],
        connections_closed=outcome.connections_closed,
    )


def _find_canonical(
    session: Session, models: CleanupEntityModels, *, stylebook_id: int, canonical_id: str
) -> Any:
    canonical = session.get(models.canonical, canonical_id)
    if canonical is None or int(canonical.stylebook_id) != int(stylebook_id):
        return None
    return canonical


def _activity(item: _RemovalItemFields, run_id: str, caller: ActionCaller) -> RemovalActivity:
    return RemovalActivity(
        actor_type="agent",
        source=ACTIVITY_SOURCE,
        payload={
            "run_id": run_id,
            "client_item_id": item.item_id,
            "credential_id": caller.credential_id,
            "credential_label": caller.credential_label,
            "reason_code": item.mention_reason_code,
            "provenance": item.provenance,
        },
    )


def _finish_item(
    session: Session,
    models: CleanupEntityModels,
    *,
    operation: str,
    action: Literal["retire", "reinstate", "delete"],
    item: _RemovalItemFields,
    outcome: RemovalOutcome,
    before_state: RemovalBeforeState,
    stylebook_id: int,
    run_id: str,
    caller: ActionCaller,
    dry_run: bool,
    reindex: ReindexEntity | None,
) -> RemovalApplyResult:
    summary = _summary(action, item, outcome)
    if dry_run:
        return RemovalApplyResult(item_id=item.item_id, status="would_apply", summary=summary)
    queued = False
    if reindex is not None:
        for project_id, record_id in outcome.released_records:
            reindex(
                session,
                project_id=project_id,
                entity_type=models.singular,
                entity_id=record_id,
            )
            queued = True
    try:
        recorded = record_action(
            session,
            run_id=run_id,
            stylebook_id=stylebook_id,
            operation=operation,
            entity_type=models.singular,
            canonical_id=item.canonical_id,
            related_canonical_id=None,
            client_item_id=item.item_id,
            provenance=item.provenance,
            caller=caller,
            request=item,
            result=summary,
            before_state=before_state,
            reindex_queued=queued,
        )
    except Exception as exc:
        raise LedgerError from exc
    return RemovalApplyResult(
        item_id=item.item_id,
        status="applied",
        action_id=str(recorded.id),
        reindex_queued=queued,
        summary=summary,
    )


def _before_state(
    session: Session,
    models: CleanupEntityModels,
    *,
    operation: str,
    stylebook_id: int,
    organization_id: int,
    canonical_id: str,
) -> RemovalBeforeState:
    return RemovalBeforeState(
        operation=operation,
        entity_type=models.singular,
        canonical=capture_canonical_before_state(
            session,
            models,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            canonical_id=canonical_id,
        ),
        released_records=[],
    )


def _apply_retirement(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    organization_id: int,
    run_id: str,
    item: RetirementApplyItem,
    dry_run: bool,
    caller: ActionCaller,
    reindex: ReindexEntity | None,
) -> RemovalApplyResult:
    not_open = run_not_open_refusal(session, stylebook_id=stylebook_id, run_id=run_id)
    if not_open is not None:
        raise not_open
    canonical = _find_canonical(
        session, models, stylebook_id=stylebook_id, canonical_id=item.canonical_id
    )
    if canonical is None:
        raise ItemRefused(
            REASON_NOT_FOUND, f"Canonical {item.canonical_id} is not in this Stylebook."
        )
    inactive = str(canonical.status) == STATUS_INACTIVE
    if item.action == "retire" and inactive:
        return RemovalApplyResult(
            item_id=item.item_id,
            status="noop",
            reason=REASON_ALREADY_INACTIVE,
            message="This record is already retired.",
        )
    if item.action == "reinstate" and not inactive:
        return RemovalApplyResult(
            item_id=item.item_id,
            status="noop",
            reason=REASON_ALREADY_ACTIVE,
            message="This record is already active.",
        )
    refusal = ceiling_refusal(
        session, run_id=run_id, operation=RETIREMENT, noun="retirements and reinstatements"
    )
    if refusal is not None:
        raise refusal

    before_state = _before_state(
        session,
        models,
        operation=RETIREMENT,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        canonical_id=item.canonical_id,
    )
    activity = None if dry_run else _activity(item, run_id, caller)
    if item.action == "reinstate":
        outcome = reinstate_canonical(
            session, models, canonical, stylebook_id=stylebook_id, activity=activity
        )
    else:
        linked = linked_records_for_canonical(
            session, models, organization_id=organization_id, canonical_id=item.canonical_id
        )
        outcome = retire_canonical(
            session,
            models,
            canonical,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            disposition=_release_disposition(item, len(linked)),
            reason_code=_reason_code(item, RETIRED_RELEASE_REASON),
            activity=activity,
        )
        before_state.released_records = outcome.released_before
    return _finish_item(
        session,
        models,
        operation=RETIREMENT,
        action=item.action,
        item=item,
        outcome=outcome,
        before_state=before_state,
        stylebook_id=stylebook_id,
        run_id=run_id,
        caller=caller,
        dry_run=dry_run,
        reindex=reindex,
    )


def _apply_deletion(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    organization_id: int,
    run_id: str,
    item: DeletionApplyItem,
    dry_run: bool,
    caller: ActionCaller,
    reindex: ReindexEntity | None,
) -> RemovalApplyResult:
    not_open = run_not_open_refusal(session, stylebook_id=stylebook_id, run_id=run_id)
    if not_open is not None:
        raise not_open
    canonical = _find_canonical(
        session, models, stylebook_id=stylebook_id, canonical_id=item.canonical_id
    )
    if canonical is None:
        if was_deleted_by_cleanup_run(
            session,
            stylebook_id=stylebook_id,
            entity_type=models.singular,
            canonical_id=item.canonical_id,
        ):
            return RemovalApplyResult(
                item_id=item.item_id,
                status="noop",
                reason=REASON_ALREADY_DELETED,
                message="This record was already deleted.",
            )
        raise ItemRefused(
            REASON_NOT_FOUND, f"Canonical {item.canonical_id} is not in this Stylebook."
        )
    refusal = ceiling_refusal(session, run_id=run_id, operation=DELETION, noun="deletions")
    if refusal is not None:
        raise refusal
    linked = linked_records_for_canonical(
        session, models, organization_id=organization_id, canonical_id=item.canonical_id
    )
    disposition = _release_disposition(item, len(linked))

    before_state = _before_state(
        session,
        models,
        operation=DELETION,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        canonical_id=item.canonical_id,
    )
    outcome = delete_canonical(
        session,
        models,
        canonical,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        disposition=disposition,
        reason_code=_reason_code(item, DELETED_RELEASE_REASON),
        activity=None if dry_run else _activity(item, run_id, caller),
    )
    before_state.released_records = outcome.released_before
    return _finish_item(
        session,
        models,
        operation=DELETION,
        action="delete",
        item=item,
        outcome=outcome,
        before_state=before_state,
        stylebook_id=stylebook_id,
        run_id=run_id,
        caller=caller,
        dry_run=dry_run,
        reindex=reindex,
    )


def apply_retirement_items(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    organization_id: int,
    body: RetirementRequestBody,
    caller: ActionCaller,
    reindex: ReindexEntity | None,
) -> RemovalResponse:
    """Process every item in order and report each one.

    Raises ``RunNotFoundError`` when the run is not in this Stylebook. Commits per item.
    """
    require_run(session, stylebook_id=stylebook_id, run_id=body.run_id)
    results = process_items(
        session,
        items=body.items,
        operation_noun="retirement",
        apply_one=lambda item: _apply_retirement(
            session,
            models,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            run_id=body.run_id,
            item=item,
            dry_run=body.dry_run,
            caller=caller,
            reindex=reindex,
        ),
        error_result=_error,
    )
    return _response(body.run_id, body.dry_run, results)


def apply_deletion_items(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    organization_id: int,
    body: DeletionRequestBody,
    caller: ActionCaller,
    reindex: ReindexEntity | None,
) -> RemovalResponse:
    """Process every item in order and report each one.

    Raises ``RunNotFoundError`` when the run is not in this Stylebook. Commits per item.
    """
    require_run(session, stylebook_id=stylebook_id, run_id=body.run_id)
    results = process_items(
        session,
        items=body.items,
        operation_noun="deletion",
        apply_one=lambda item: _apply_deletion(
            session,
            models,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            run_id=body.run_id,
            item=item,
            dry_run=body.dry_run,
            caller=caller,
            reindex=reindex,
        ),
        error_result=_error,
    )
    return _response(body.run_id, body.dry_run, results)


def _response(run_id: str, dry_run: bool, results: list[RemovalApplyResult]) -> RemovalResponse:
    return RemovalResponse(
        run_id=run_id,
        dry_run=dry_run,
        counts=count_statuses([r.status for r in results]),
        items=results,
    )
