"""The candidate decisions route's item pipeline.

A candidate is a project record waiting for a canonical. A decision links it to an existing record
(`link`), makes a new record from it (`create`), or sets it aside (`defer`). The Stylebook app's
accept and defer buttons use the same library functions (``decision_ops``).
"""

from __future__ import annotations

from typing import Any, Literal

from backfield_db import StylebookCleanupAction
from pydantic import BaseModel, Field, JsonValue
from sqlmodel import Session, select

from backfield_entities.activity import (
    EVENT_CANDIDATE_DEFERRED,
    EVENT_CANONICAL_CREATED,
    EVENT_SUBSTRATE_LINKED,
    log_stylebook_activity,
)
from backfield_entities.canonical.link import CANONICAL_LINK_WAIVED
from backfield_entities.cleanup.apply_merge import ReindexEntity
from backfield_entities.cleanup.before_state import (
    BEFORE_STATE_SCHEMA_VERSION,
    RowJson,
    row_to_json,
)
from backfield_entities.cleanup.candidates import stylebook_project_ids
from backfield_entities.cleanup.decision_ops import (
    CandidateCanonicalElsewhereError,
    CandidateCanonicalNotFoundError,
    CandidateDecisionError,
    CandidateInvalidError,
    create_candidate_canonical,
    defer_candidate,
    link_candidate,
)
from backfield_entities.cleanup.entity_models import CleanupEntityModels
from backfield_entities.cleanup.envelope import (
    MAX_ITEM_ID_LENGTH,
    MAX_ITEMS_PER_REQUEST,
    REASON_ALREADY_DEFERRED,
    REASON_ALREADY_LINKED,
    REASON_GUARD_REFUSED,
    REASON_INVALID_ITEM,
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

OPERATION = "decision"
ACTIVITY_SOURCE = "cleanup_api"

DecisionAction = Literal["link", "create", "defer"]


class DecisionApplyItem(BaseModel):
    item_id: str = Field(
        min_length=1,
        max_length=MAX_ITEM_ID_LENGTH,
        description="Your own id for this item; echoed back and stored with the action.",
    )
    candidate_id: int = Field(description="The candidate's id, from the candidates list.")
    action: DecisionAction = Field(
        description=(
            "`link` to an existing record (needs `canonical_id`), `create` a new record from the "
            "candidate, or `defer` it."
        )
    )
    canonical_id: str | None = Field(
        default=None, description="With `link`: the record to link the candidate to."
    )
    name: str | None = Field(
        default=None,
        description="With `create`: the new record's name. Defaults to the candidate's.",
    )
    kind: str | None = Field(
        default=None,
        description=(
            "With `create`: the place kind, person type or organization type. Defaults to the "
            "candidate's."
        ),
    )
    geometry: dict[str, JsonValue] | None = Field(
        default=None,
        description="With `create` for locations: GeoJSON geography. Defaults to the candidate's.",
    )
    provenance: dict[str, JsonValue] | None = Field(
        default=None, description="Anything you want stored with the action, as given."
    )


class DecisionRequestBody(BaseModel):
    run_id: str = Field(min_length=1)
    dry_run: bool = Field(
        default=True, description="Report what would happen without changing anything."
    )
    items: list[DecisionApplyItem] = Field(min_length=1, max_length=MAX_ITEMS_PER_REQUEST)


class DecisionSummary(BaseModel):
    candidate_id: int
    candidate_name: str
    action: DecisionAction
    canonical_id: str | None = Field(
        default=None, description="The record it is now linked to; empty after `defer`."
    )
    canonical_label: str | None = None
    created: bool = Field(default=False, description="True when `create` made a new record.")


class DecisionApplyResult(ItemResult):
    summary: DecisionSummary | None = None


class DecisionResponse(BaseModel):
    run_id: str
    dry_run: bool
    counts: ApplyCounts
    items: list[DecisionApplyResult]


class DecisionBeforeState(BaseModel):
    """The candidate as it was, and the names the target already had (for a link)."""

    schema_version: int = BEFORE_STATE_SCHEMA_VERSION
    operation: str = OPERATION
    entity_type: str
    candidate: RowJson
    target_alias_norms: list[str] = Field(default_factory=list)


def _error(item: DecisionApplyItem, reason: str, message: str) -> DecisionApplyResult:
    return DecisionApplyResult(item_id=item.item_id, status="error", reason=reason, message=message)


def _invalid(message: str) -> ItemRefused:
    return ItemRefused(REASON_INVALID_ITEM, message)


def _check_item_fields(item: DecisionApplyItem, models: CleanupEntityModels) -> None:
    """Refuse fields that do not belong to the action, so a typo never silently does less."""
    if item.action == "link":
        if not item.canonical_id:
            raise _invalid("`link` needs `canonical_id`.")
        extras = [f for f in ("name", "kind", "geometry") if getattr(item, f) is not None]
        if extras:
            raise _invalid(f"`link` does not take {', '.join(f'`{f}`' for f in extras)}.")
        return
    if item.canonical_id is not None:
        raise _invalid(f"`{item.action}` does not take `canonical_id`.")
    if item.action == "defer":
        extras = [f for f in ("name", "kind", "geometry") if getattr(item, f) is not None]
        if extras:
            raise _invalid(f"`defer` does not take {', '.join(f'`{f}`' for f in extras)}.")
    elif item.geometry is not None and models.name != "locations":
        raise _invalid("`geometry` only applies to locations.")


def _find_candidate(
    session: Session,
    models: CleanupEntityModels,
    *,
    item: DecisionApplyItem,
    project_ids: list[int],
) -> Any:
    candidate = session.get(models.substrate, item.candidate_id)
    if candidate is None or int(candidate.project_id) not in project_ids:
        raise ItemRefused(
            REASON_NOT_FOUND, f"Candidate {item.candidate_id} is not in this Stylebook."
        )
    return candidate


def _linked_canonical_id(models: CleanupEntityModels, candidate: Any) -> str | None:
    value = getattr(candidate, models.substrate_canonical_column)
    return str(value) if value is not None else None


def _already_decided(
    session: Session,
    models: CleanupEntityModels,
    *,
    item: DecisionApplyItem,
    run_id: str,
    candidate: Any,
) -> DecisionApplyResult | None:
    """A noop result when this exact decision already stands, so a retry is safe."""
    linked_to = _linked_canonical_id(models, candidate)
    if item.action == "defer":
        if linked_to is None and candidate.canonical_link_status == CANONICAL_LINK_WAIVED:
            return _noop(item, REASON_ALREADY_DEFERRED, "This candidate is already deferred.")
        return None
    if linked_to is None:
        return None
    if item.action == "link" and linked_to == item.canonical_id:
        return _noop(item, REASON_ALREADY_LINKED, "This candidate is already linked to it.")
    if item.action == "create" and _applied_earlier(session, run_id=run_id, item=item):
        return _noop(item, REASON_ALREADY_LINKED, "A record was already created from this one.")
    return None


def _applied_earlier(session: Session, *, run_id: str, item: DecisionApplyItem) -> bool:
    """True when this run's ledger holds a decision with the same item id for this candidate."""
    earlier = session.exec(
        select(StylebookCleanupAction.request_json).where(
            StylebookCleanupAction.run_id == run_id,
            StylebookCleanupAction.operation == OPERATION,
            StylebookCleanupAction.client_item_id == item.item_id,
        )
    ).all()
    return any(row.get("candidate_id") == item.candidate_id for row in earlier)


def _noop(item: DecisionApplyItem, reason: str, message: str) -> DecisionApplyResult:
    return DecisionApplyResult(item_id=item.item_id, status="noop", reason=reason, message=message)


def _refuse_inactive_target(
    session: Session, models: CleanupEntityModels, *, stylebook_id: int, canonical_id: str
) -> None:
    """Retired records stop matching new mentions, so nothing may be linked to one."""
    canonical = session.get(models.canonical, canonical_id)
    if (
        canonical is not None
        and int(canonical.stylebook_id) == int(stylebook_id)
        and str(canonical.status) != "active"
    ):
        raise ItemRefused(
            REASON_GUARD_REFUSED,
            "That record is retired. Reinstate it before linking candidates to it.",
        )


def _before_state(
    session: Session, models: CleanupEntityModels, *, item: DecisionApplyItem, candidate: Any
) -> DecisionBeforeState:
    alias_norms: list[str] = []
    if item.action == "link" and item.canonical_id:
        alias_column = models.column(models.alias, models.alias_canonical_column)
        rows = session.exec(select(models.alias).where(alias_column == item.canonical_id)).all()
        alias_norms = sorted(str(row.normalized_alias) for row in rows)
    return DecisionBeforeState(
        entity_type=models.singular,
        candidate=row_to_json(candidate),
        target_alias_norms=alias_norms,
    )


def _carry_out(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    item: DecisionApplyItem,
    candidate: Any,
) -> tuple[str | None, bool]:
    """Run the decision; returns the canonical id (None for defer) and whether one was created."""
    try:
        if item.action == "defer":
            defer_candidate(session, models, candidate, provenance=CLEANUP_API_ALIAS_PROVENANCE)
            return None, False
        if item.action == "link":
            canonical_id = link_candidate(
                session,
                models,
                candidate,
                stylebook_id=stylebook_id,
                canonical_id=str(item.canonical_id),
                provenance=CLEANUP_API_ALIAS_PROVENANCE,
            )
            return canonical_id, False
        canonical_id = create_candidate_canonical(
            session,
            models,
            candidate,
            stylebook_id=stylebook_id,
            name=item.name,
            kind=item.kind,
            geometry_json=dict(item.geometry) if item.geometry is not None else None,
            provenance=CLEANUP_API_ALIAS_PROVENANCE,
        )
        return canonical_id, True
    except (CandidateCanonicalNotFoundError, CandidateCanonicalElsewhereError) as exc:
        raise ItemRefused(REASON_NOT_FOUND, f"{exc} Check `canonical_id`.") from exc
    except CandidateInvalidError as exc:
        raise ItemRefused(REASON_INVALID_ITEM, str(exc)) from exc
    except CandidateDecisionError as exc:
        raise ItemRefused(REASON_GUARD_REFUSED, str(exc)) from exc


def _write_activity(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    run_id: str,
    item: DecisionApplyItem,
    candidate: Any,
    summary: DecisionSummary,
    caller: ActionCaller,
) -> None:
    event_type = {
        "link": EVENT_SUBSTRATE_LINKED,
        "create": EVENT_CANONICAL_CREATED,
        "defer": EVENT_CANDIDATE_DEFERRED,
    }[item.action]
    log_stylebook_activity(
        session,
        stylebook_id=stylebook_id,
        actor_type="agent",
        source=ACTIVITY_SOURCE,
        event_type=event_type,
        project_id=int(candidate.project_id),
        entity_type=models.singular,
        entity_id=summary.canonical_id,
        entity_label=summary.canonical_label,
        payload_json={
            "run_id": run_id,
            "client_item_id": item.item_id,
            "credential_id": caller.credential_id,
            "credential_label": caller.credential_label,
            "candidate_id": item.candidate_id,
            "candidate_name": summary.candidate_name,
            "action": item.action,
            "provenance": item.provenance,
        },
    )


def _apply_decision(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    project_ids: list[int],
    run_id: str,
    item: DecisionApplyItem,
    dry_run: bool,
    caller: ActionCaller,
    reindex: ReindexEntity | None,
) -> DecisionApplyResult:
    not_open = run_not_open_refusal(session, stylebook_id=stylebook_id, run_id=run_id)
    if not_open is not None:
        raise not_open
    _check_item_fields(item, models)
    candidate = _find_candidate(session, models, item=item, project_ids=project_ids)
    already = _already_decided(session, models, item=item, run_id=run_id, candidate=candidate)
    if already is not None:
        return already
    refusal = ceiling_refusal(session, run_id=run_id, operation=OPERATION, noun="decisions")
    if refusal is not None:
        raise refusal
    if item.action == "link":
        _refuse_inactive_target(
            session, models, stylebook_id=stylebook_id, canonical_id=str(item.canonical_id)
        )

    before_state = _before_state(session, models, item=item, candidate=candidate)
    candidate_name = str(candidate.name)
    project_id = int(candidate.project_id)
    canonical_id, created = _carry_out(
        session, models, stylebook_id=stylebook_id, item=item, candidate=candidate
    )
    canonical = session.get(models.canonical, canonical_id) if canonical_id else None
    summary = DecisionSummary(
        candidate_id=item.candidate_id,
        candidate_name=candidate_name,
        action=item.action,
        canonical_id=canonical_id,
        canonical_label=str(canonical.label) if canonical is not None else None,
        created=created,
    )
    if dry_run:
        return DecisionApplyResult(item_id=item.item_id, status="would_apply", summary=summary)

    _write_activity(
        session,
        models,
        stylebook_id=stylebook_id,
        run_id=run_id,
        item=item,
        candidate=candidate,
        summary=summary,
        caller=caller,
    )
    queued = False
    if reindex is not None and canonical_id is not None:
        reindex(
            session, project_id=project_id, entity_type=models.singular, entity_id=item.candidate_id
        )
        queued = True
    try:
        recorded = record_action(
            session,
            run_id=run_id,
            stylebook_id=stylebook_id,
            operation=OPERATION,
            entity_type=models.singular,
            canonical_id=canonical_id,
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
    return DecisionApplyResult(
        item_id=item.item_id,
        status="applied",
        action_id=str(recorded.id),
        reindex_queued=queued,
        summary=summary,
    )


def apply_decision_items(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    organization_id: int,
    body: DecisionRequestBody,
    caller: ActionCaller,
    reindex: ReindexEntity | None,
) -> DecisionResponse:
    """Process every item in order and report each one.

    Raises ``RunNotFoundError`` when the run is not in this Stylebook. Commits per item.
    """
    require_run(session, stylebook_id=stylebook_id, run_id=body.run_id)
    project_ids = stylebook_project_ids(
        session, stylebook_id=stylebook_id, organization_id=organization_id
    )
    results = process_items(
        session,
        items=body.items,
        operation_noun="decision",
        apply_one=lambda item: _apply_decision(
            session,
            models,
            stylebook_id=stylebook_id,
            project_ids=project_ids,
            run_id=body.run_id,
            item=item,
            dry_run=body.dry_run,
            caller=caller,
            reindex=reindex,
        ),
        error_result=_error,
    )
    return DecisionResponse(
        run_id=body.run_id,
        dry_run=body.dry_run,
        counts=count_statuses([r.status for r in results]),
        items=results,
    )
