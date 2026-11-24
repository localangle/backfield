"""The edits route's item pipeline: change a canonical's own fields, one item at a time.

A rename keeps the old name as an alias. A location's geography can be set or cleared, and can
optionally be copied onto the saved places linked to it that should follow it.
"""

from __future__ import annotations

from typing import Any

from backfield_db import BackfieldProject, SubstrateLocation
from backfield_events import record_canonical_updated
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError
from sqlmodel import Session, col, select

from backfield_entities.activity import EVENT_CANONICAL_UPDATED, log_stylebook_activity
from backfield_entities.cleanup.alias_ops import touch_canonical
from backfield_entities.cleanup.before_state import (
    BEFORE_STATE_SCHEMA_VERSION,
    RowJson,
    row_to_json,
)
from backfield_entities.cleanup.edit_ops import EDITABLE_FIELDS, apply_field_edits
from backfield_entities.cleanup.entity_models import CleanupEntityModels
from backfield_entities.cleanup.envelope import (
    MAX_ITEM_ID_LENGTH,
    MAX_ITEMS_PER_REQUEST,
    REASON_INVALID_ITEM,
    REASON_NO_CHANGE,
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
from backfield_entities.entities.location.geometry_apply import (
    apply_canonical_geometry_to_substrates,
    suggest_substrate_for_geometry_apply,
)
from backfield_entities.geo.geometry_bind import assign_geojson_geometry

OPERATION = "edit"
ACTIVITY_SOURCE = "cleanup_api"
GEOMETRY_COLUMNS = ("geometry_json", "geometry_type", "h3_cell", "h3_resolution")


class LocationChanges(BaseModel):
    """Fields a location edit may change. Leave a field out to keep it; `null` clears it."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    location_type: str | None = None
    formatted_address: str | None = None
    geometry: dict[str, JsonValue] | None = Field(
        default=None, description="GeoJSON geography to store; `null` clears the stored one."
    )


class PersonChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    person_type: str | None = None
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool | None = None
    sort_key: str | None = None


class OrganizationChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    organization_type: str | None = None


CHANGE_MODELS: dict[str, type[BaseModel]] = {
    "location": LocationChanges,
    "person": PersonChanges,
    "organization": OrganizationChanges,
}


class EditApplyItem(BaseModel):
    item_id: str = Field(
        min_length=1,
        max_length=MAX_ITEM_ID_LENGTH,
        description="Your own id for this item; echoed back and stored with the action.",
    )
    canonical_id: str = Field(min_length=1)
    changes: dict[str, JsonValue] = Field(
        default_factory=dict,
        description=(
            "The fields to change. Locations: `label`, `location_type`, `formatted_address`, "
            "`geometry`. People: `label`, `person_type`, `title`, `affiliation`, "
            "`public_figure`, `sort_key`. Organizations: `label`, `organization_type`. "
            "Changing `label` keeps the old name as an alias."
        ),
    )
    apply_geometry_to_saved_places: bool = Field(
        default=False,
        description=(
            "Locations only: also copy the record's geography onto the saved places linked to "
            "it that should follow it."
        ),
    )
    provenance: dict[str, JsonValue] | None = Field(
        default=None, description="Anything you want stored with the action, as given."
    )


class EditRequestBody(BaseModel):
    run_id: str = Field(min_length=1)
    dry_run: bool = Field(
        default=True, description="Report what would happen without changing anything."
    )
    items: list[EditApplyItem] = Field(min_length=1, max_length=MAX_ITEMS_PER_REQUEST)


class EditSummary(BaseModel):
    canonical_id: str
    canonical_label: str
    changed_fields: list[str]
    before: dict[str, JsonValue] = Field(description="The changed fields as they were.")
    after: dict[str, JsonValue] = Field(description="The changed fields as they are now.")
    old_name_kept_as_alias: bool
    saved_places_updated: list[int] = Field(
        description="Saved places that took the record's geography."
    )


class EditApplyResult(ItemResult):
    summary: EditSummary | None = None


class EditResponse(BaseModel):
    run_id: str
    dry_run: bool
    counts: ApplyCounts
    items: list[EditApplyResult]


class EditBeforeState(BaseModel):
    """Everything an edit changed, as it was; alias rows created are listed by id."""

    schema_version: int = BEFORE_STATE_SCHEMA_VERSION
    fields: dict[str, JsonValue]
    geometry: dict[str, JsonValue] | None
    alias_rows_before: list[RowJson]
    created_alias_ids: list[int]
    saved_places: list[RowJson]


def _error(item: EditApplyItem, reason: str, message: str) -> EditApplyResult:
    return EditApplyResult(item_id=item.item_id, status="error", reason=reason, message=message)


def _parse_changes(models: CleanupEntityModels, item: EditApplyItem) -> BaseModel:
    """The item's changes as the entity's change model; refuses fields it does not allow."""
    try:
        parsed = CHANGE_MODELS[models.singular].model_validate(item.changes)
    except ValidationError as exc:
        first = exc.errors()[0]
        field_name = ".".join(str(part) for part in first["loc"]) or "changes"
        allowed = ", ".join(_allowed_fields(models))
        raise ItemRefused(
            REASON_INVALID_ITEM,
            f"Cannot use `{field_name}` ({first['msg']}). Allowed fields: {allowed}.",
        ) from exc
    if item.apply_geometry_to_saved_places and models.singular != "location":
        raise ItemRefused(
            REASON_INVALID_ITEM, "Only locations have geography to copy onto saved places."
        )
    if not parsed.model_fields_set and not item.apply_geometry_to_saved_places:
        raise ItemRefused(REASON_INVALID_ITEM, "No changes were given.")
    return parsed


def _allowed_fields(models: CleanupEntityModels) -> tuple[str, ...]:
    extra = ("geometry",) if models.singular == "location" else ()
    return EDITABLE_FIELDS[models.singular] + extra


def _field_updates(parsed: BaseModel) -> dict[str, object]:
    """The fields the caller named, minus geometry (which has its own handling)."""
    return {name: getattr(parsed, name) for name in parsed.model_fields_set if name != "geometry"}


def _geometry_columns(canonical: Any) -> dict[str, JsonValue]:
    return {name: getattr(canonical, name) for name in GEOMETRY_COLUMNS}


def _set_geometry(session: Session, canonical: Any, geometry: dict[str, JsonValue] | None) -> bool:
    """Store (or clear) the geography. Returns True when it differs from what was stored."""
    if canonical.geometry_json == geometry:
        return False
    assign_geojson_geometry(session, canonical, geometry)
    return True


def _organization_project_ids(session: Session, organization_id: int) -> list[int]:
    return [
        int(project_id)
        for project_id in session.exec(
            select(BackfieldProject.id).where(BackfieldProject.organization_id == organization_id)
        ).all()
        if project_id is not None
    ]


def _saved_places_to_update(
    session: Session, canonical: Any, *, organization_id: int
) -> list[SubstrateLocation]:
    """Linked saved places that should follow the record's geography and do not yet."""
    project_ids = _organization_project_ids(session, organization_id)
    if not project_ids or not isinstance(canonical.geometry_json, dict):
        return []
    linked = session.exec(
        select(SubstrateLocation).where(
            SubstrateLocation.stylebook_location_canonical_id == str(canonical.id),
            col(SubstrateLocation.project_id).in_(project_ids),
        )
    ).all()
    return [
        place
        for place in linked
        if place.geometry_json != canonical.geometry_json
        and suggest_substrate_for_geometry_apply(
            substrate_location_type=place.location_type,
            canonical_location_type=canonical.location_type,
        )
    ]


def _saved_place_before(place: SubstrateLocation) -> RowJson:
    columns = (*GEOMETRY_COLUMNS, "source_details_json")
    values = row_to_json(place)
    return {"id": values["id"], **{name: values[name] for name in columns}}


def _apply_item(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    organization_id: int,
    run_id: str,
    item: EditApplyItem,
    dry_run: bool,
    caller: ActionCaller,
) -> EditApplyResult:
    """Do one item; the driver commits an applied result and rolls back everything else."""
    not_open = run_not_open_refusal(session, stylebook_id=stylebook_id, run_id=run_id)
    if not_open is not None:
        raise not_open
    canonical = session.get(models.canonical, item.canonical_id)
    if canonical is None or int(canonical.stylebook_id) != int(stylebook_id):
        raise ItemRefused(
            REASON_NOT_FOUND, f"Canonical {item.canonical_id} is not in this Stylebook."
        )
    parsed = _parse_changes(models, item)
    refusal = ceiling_refusal(session, run_id=run_id, operation=OPERATION, noun="edits")
    if refusal is not None:
        raise refusal

    geometry_before = _geometry_columns(canonical) if models.singular == "location" else None
    outcome = apply_field_edits(
        session,
        models,
        canonical,
        _field_updates(parsed),
        old_label_alias_provenance=CLEANUP_API_ALIAS_PROVENANCE,
    )
    geometry_changed = False
    if "geometry" in parsed.model_fields_set:
        geometry_changed = _set_geometry(session, canonical, getattr(parsed, "geometry"))
    saved_places: list[SubstrateLocation] = []
    saved_places_before: list[RowJson] = []
    if item.apply_geometry_to_saved_places:
        if not isinstance(canonical.geometry_json, dict):
            raise ItemRefused(
                REASON_INVALID_ITEM, "This record has no geography to copy onto saved places."
            )
        saved_places = _saved_places_to_update(session, canonical, organization_id=organization_id)
        saved_places_before = [_saved_place_before(place) for place in saved_places]
        if saved_places:
            apply_canonical_geometry_to_substrates(
                session,
                canon=canonical,
                substrate_ids=[int(place.id) for place in saved_places],
                visible_project_ids=_organization_project_ids(session, organization_id),
            )
    if geometry_changed:
        outcome.before["geometry"] = (geometry_before or {}).get("geometry_json")
        outcome.after["geometry"] = canonical.geometry_json
        touch_canonical(canonical)
    if not outcome.after and not saved_places:
        return EditApplyResult(
            item_id=item.item_id,
            status="noop",
            reason=REASON_NO_CHANGE,
            message="Everything given already matches the record.",
        )

    summary = EditSummary(
        canonical_id=item.canonical_id,
        canonical_label=str(canonical.label),
        changed_fields=outcome.changed_fields,
        before=outcome.before,
        after=outcome.after,
        old_name_kept_as_alias=outcome.old_label is not None,
        saved_places_updated=[int(place.id) for place in saved_places],
    )
    if dry_run:
        return EditApplyResult(item_id=item.item_id, status="would_apply", summary=summary)

    alias_change = outcome.old_label_alias
    _record_activity(session, models, canonical, summary, item, run_id, stylebook_id, caller)
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
            before_state=EditBeforeState(
                fields={k: v for k, v in outcome.before.items() if k != "geometry"},
                geometry=geometry_before if geometry_changed else None,
                alias_rows_before=alias_change.rows_before if alias_change else [],
                created_alias_ids=alias_change.created_alias_ids if alias_change else [],
                saved_places=saved_places_before,
            ),
            reindex_queued=False,
        )
    except Exception as exc:
        raise LedgerError from exc
    return EditApplyResult(
        item_id=item.item_id, status="applied", action_id=str(action.id), summary=summary
    )


def _record_activity(
    session: Session,
    models: CleanupEntityModels,
    canonical: Any,
    summary: EditSummary,
    item: EditApplyItem,
    run_id: str,
    stylebook_id: int,
    caller: ActionCaller,
) -> None:
    label = str(canonical.label)
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
            "changed_fields": summary.changed_fields,
            "geometry_updated": "geometry" in summary.after,
            "saved_places_updated": summary.saved_places_updated,
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


def apply_edit_items(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    organization_id: int,
    body: EditRequestBody,
    caller: ActionCaller,
) -> EditResponse:
    """Process every item in order and report each one.

    Raises ``RunNotFoundError`` when the run is not in this Stylebook. Commits per item.
    """
    require_run(session, stylebook_id=stylebook_id, run_id=body.run_id)
    results = process_items(
        session,
        items=body.items,
        operation_noun="edit",
        apply_one=lambda item: _apply_item(
            session,
            models,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            run_id=body.run_id,
            item=item,
            dry_run=body.dry_run,
            caller=caller,
        ),
        error_result=_error,
    )
    return EditResponse(
        run_id=body.run_id,
        dry_run=body.dry_run,
        counts=count_statuses([r.status for r in results]),
        items=results,
    )
