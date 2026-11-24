"""The merges route's item pipeline: guards, ceiling, before-state, apply, then the ledger.

Each item commits (or rolls back) on its own, so one failing merge never undoes the others. A dry
run does the real work inside the item's transaction and rolls it back, so it reports exactly what
an apply would do and writes nothing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, JsonValue
from sqlmodel import Session

from backfield_entities.cleanup.apply_merge import (
    MergeActivity,
    MergeOutcome,
    MergeRequest,
    ReindexEntity,
    apply_merge,
)
from backfield_entities.cleanup.before_state import capture_merge_before_state
from backfield_entities.cleanup.entity_models import CleanupEntityModels
from backfield_entities.cleanup.envelope import (
    MAX_ITEM_ID_LENGTH,
    MAX_ITEMS_PER_REQUEST,
    REASON_ALREADY_MERGED,
    REASON_NOT_FOUND,
    REASON_SAME_CANONICAL,
    ApplyCounts,
    ItemResult,
    count_statuses,
)
from backfield_entities.cleanup.item_driver import (
    LedgerError,
    ceiling_refusal,
    process_items,
    run_not_open_refusal,
)
from backfield_entities.cleanup.ledger import ActionCaller, record_action
from backfield_entities.cleanup.redirects import link_redirect_to_action, resolve_canonical
from backfield_entities.cleanup.runs import require_run
from backfield_entities.entities.location.merge import GeometryWinner

OPERATION = "merge"
ACTIVITY_SOURCE = "cleanup_api"


class MergeItem(BaseModel):
    item_id: str = Field(
        min_length=1,
        max_length=MAX_ITEM_ID_LENGTH,
        description="Your own id for this item; echoed back and stored with the action.",
    )
    source_id: str = Field(min_length=1, description="The canonical to merge away.")
    target_id: str = Field(min_length=1, description="The canonical that survives.")
    resolved_type: str | None = Field(
        default=None,
        description="Kind to use when the two disagree (people and organizations).",
    )
    geometry_winner: GeometryWinner = Field(
        default="target",
        description="Locations only: whose geography wins when both records have one.",
    )
    provenance: dict[str, JsonValue] | None = Field(
        default=None, description="Anything you want stored with the action, as given."
    )


class MergeRequestBody(BaseModel):
    run_id: str = Field(min_length=1)
    dry_run: bool = Field(
        default=True, description="Report what would happen without changing anything."
    )
    items: list[MergeItem] = Field(min_length=1, max_length=MAX_ITEMS_PER_REQUEST)


class MergeSummary(BaseModel):
    source_id: str
    target_id: str
    source_label: str | None
    target_label: str | None
    relinked_count: int
    transferred_alias_count: int
    transferred_meta_count: int
    unapplied_source_geometry: dict[str, JsonValue] | None = Field(
        default=None,
        description="Source geography the survivor did not take, so it is never lost silently.",
    )


class MergeItemResult(ItemResult):
    summary: MergeSummary | None = None


class MergeResponse(BaseModel):
    run_id: str
    dry_run: bool
    counts: ApplyCounts
    items: list[MergeItemResult]


def _summary(outcome: MergeOutcome) -> MergeSummary:
    return MergeSummary(
        source_id=outcome.source_id,
        target_id=outcome.target_id,
        source_label=outcome.source_label,
        target_label=outcome.target_label,
        relinked_count=outcome.relinked_substrate_count,
        transferred_alias_count=outcome.transferred_alias_count,
        transferred_meta_count=outcome.transferred_meta_count,
        unapplied_source_geometry=outcome.unapplied_source_geometry,
    )


def _error(item: MergeItem, reason: str, message: str) -> MergeItemResult:
    return MergeItemResult(item_id=item.item_id, status="error", reason=reason, message=message)


def _exists(
    session: Session, models: CleanupEntityModels, *, stylebook_id: int, canonical_id: str
) -> bool:
    row = session.get(models.canonical, canonical_id)
    return row is not None and int(row.stylebook_id) == int(stylebook_id)


def _precheck(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    run_id: str,
    item: MergeItem,
) -> MergeItemResult | None:
    """Everything that can end an item before any change is attempted; None means go ahead."""
    not_open = run_not_open_refusal(session, stylebook_id=stylebook_id, run_id=run_id)
    if not_open is not None:
        return _error(item, not_open.reason, not_open.message)
    if item.source_id == item.target_id:
        return _error(item, REASON_SAME_CANONICAL, "The source and the survivor are the same.")
    if not _exists(session, models, stylebook_id=stylebook_id, canonical_id=item.source_id):
        resolution = resolve_canonical(
            session,
            stylebook_id=stylebook_id,
            entity_type=models.singular,
            canonical_id=item.source_id,
        )
        if resolution.merged and resolution.resolved_id == item.target_id:
            return MergeItemResult(
                item_id=item.item_id,
                status="noop",
                reason=REASON_ALREADY_MERGED,
                message="The source was already merged into this survivor.",
            )
        return _error(item, REASON_NOT_FOUND, "The source canonical is not in this Stylebook.")
    if not _exists(session, models, stylebook_id=stylebook_id, canonical_id=item.target_id):
        return _error(item, REASON_NOT_FOUND, "The survivor canonical is not in this Stylebook.")
    at_ceiling = ceiling_refusal(session, run_id=run_id, operation=OPERATION, noun="merges")
    if at_ceiling is not None:
        return _error(item, at_ceiling.reason, at_ceiling.message)
    return None


def _apply_item(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    organization_id: int,
    run_id: str,
    item: MergeItem,
    dry_run: bool,
    caller: ActionCaller,
    reindex: ReindexEntity | None,
) -> MergeItemResult:
    """Run one item; the caller rolls back on any exception."""
    blocked = _precheck(session, models, stylebook_id=stylebook_id, run_id=run_id, item=item)
    if blocked is not None:
        return blocked
    before_state = capture_merge_before_state(
        session,
        models,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        source_canonical_id=item.source_id,
        target_canonical_id=item.target_id,
    )
    activity = MergeActivity(
        actor_type="agent",
        source=ACTIVITY_SOURCE,
        payload={
            "run_id": run_id,
            "client_item_id": item.item_id,
            "credential_id": caller.credential_id,
            "credential_label": caller.credential_label,
            "provenance": item.provenance,
        },
    )
    outcome = apply_merge(
        session,
        MergeRequest(
            entity_type=models.singular,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            source_canonical_id=item.source_id,
            target_canonical_id=item.target_id,
            resolved_type=item.resolved_type,
            geometry_winner=item.geometry_winner,
        ),
        reindex=None if dry_run else reindex,
        activity=None if dry_run else activity,
    )
    summary = _summary(outcome)
    if dry_run:
        return MergeItemResult(item_id=item.item_id, status="would_apply", summary=summary)
    queued = reindex is not None and bool(outcome.relinked_substrates)
    try:
        action = record_action(
            session,
            run_id=run_id,
            stylebook_id=stylebook_id,
            operation=OPERATION,
            entity_type=models.singular,
            canonical_id=item.source_id,
            related_canonical_id=item.target_id,
            client_item_id=item.item_id,
            provenance=item.provenance,
            caller=caller,
            request=item,
            result=summary,
            before_state=before_state,
            reindex_queued=queued,
        )
        link_redirect_to_action(
            session,
            stylebook_id=stylebook_id,
            entity_type=models.singular,
            old_id=item.source_id,
            action_id=str(action.id),
        )
    except Exception as exc:
        raise LedgerError from exc
    return MergeItemResult(
        item_id=item.item_id,
        status="applied",
        action_id=str(action.id),
        reindex_queued=queued,
        summary=summary,
    )


def apply_merge_items(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    organization_id: int,
    body: MergeRequestBody,
    caller: ActionCaller,
    reindex: ReindexEntity | None,
) -> MergeResponse:
    """Process every item in order and report each one.

    Raises ``RunNotFoundError`` when the run is not in this Stylebook. Commits per item.
    """
    require_run(session, stylebook_id=stylebook_id, run_id=body.run_id)
    results = process_items(
        session,
        items=body.items,
        operation_noun="merge",
        apply_one=lambda item: _apply_item(
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
    return MergeResponse(
        run_id=body.run_id,
        dry_run=body.dry_run,
        counts=count_statuses([r.status for r in results]),
        items=results,
    )
