"""Edit a canonical's own fields, for every entity kind.

The Stylebook UI and the cleanup API both edit through here so they behave the same. Renaming a
record keeps the old name as an alias, so mentions still using it are not flagged as mismatches.
Nothing here commits; the caller owns the transaction.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import JsonValue
from pydantic_core import to_jsonable_python
from sqlmodel import Session

from backfield_entities.cleanup.alias_ops import AliasChange, add_alias, touch_canonical
from backfield_entities.cleanup.entity_models import CleanupEntityModels
from backfield_entities.entities.organization.types import normalize_organization_type
from backfield_entities.entities.person.types import derive_person_sort_key, normalize_person_type

# A rename in the Stylebook editor keeps the old name under the same trusted provenance as a name
# an editor typed in, so link checks treat it as approved.
UI_RENAME_ALIAS_PROVENANCE = "stylebook_ui_manual"

# The fields each entity kind lets a caller change. Slugs and retirement are not editable here.
EDITABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "location": ("label", "location_type", "formatted_address"),
    "person": ("label", "person_type", "title", "affiliation", "public_figure", "sort_key"),
    "organization": ("label", "organization_type"),
}


@dataclass
class FieldEditOutcome:
    """The fields that changed, as they were and as they are now."""

    before: dict[str, JsonValue] = field(default_factory=dict)
    after: dict[str, JsonValue] = field(default_factory=dict)
    old_label: str | None = None
    # Set when a rename wrote the old name as an alias.
    old_label_alias: AliasChange | None = None

    @property
    def changed_fields(self) -> list[str]:
        return sorted(self.after)


def _clean_text(value: object) -> str | None:
    """Trimmed text, with empty text meaning none."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _new_values(
    models: CleanupEntityModels, canonical: Any, updates: Mapping[str, object]
) -> dict[str, object]:
    """The values each updated field would take, normalized the way the editor does it."""
    unknown = set(updates) - set(EDITABLE_FIELDS[models.singular])
    if unknown:
        raise ValueError(f"These fields cannot be edited here: {', '.join(sorted(unknown))}.")
    values: dict[str, object] = {}
    if updates.get("label") is not None:
        label = str(updates["label"]).strip()
        if not label:
            raise ValueError("A name cannot be empty.")
        values["label"] = label
    if models.singular == "location":
        if "location_type" in updates:
            cleaned = _clean_text(updates["location_type"])
            values["location_type"] = cleaned.lower() if cleaned else None
        if "formatted_address" in updates:
            values["formatted_address"] = _clean_text(updates["formatted_address"])
    elif models.singular == "person":
        _add_person_values(values, canonical, updates)
    elif "organization_type" in updates:
        raw = updates["organization_type"]
        values["organization_type"] = normalize_organization_type(_clean_text(raw))
    return values


def _add_person_values(
    values: dict[str, object], canonical: Any, updates: Mapping[str, object]
) -> None:
    if "person_type" in updates:
        values["person_type"] = normalize_person_type(_clean_text(updates["person_type"]))
    if "title" in updates:
        values["title"] = _clean_text(updates["title"])
    if "affiliation" in updates:
        values["affiliation"] = _clean_text(updates["affiliation"])
    if updates.get("public_figure") is not None:
        values["public_figure"] = bool(updates["public_figure"])
    label = str(values.get("label", canonical.label))
    if "sort_key" in updates:
        values["sort_key"] = derive_person_sort_key(
            label, explicit=_clean_text(updates["sort_key"])
        )
    elif "label" in values:
        values["sort_key"] = derive_person_sort_key(label)


def apply_field_edits(
    session: Session,
    models: CleanupEntityModels,
    canonical: Any,
    updates: Mapping[str, object],
    *,
    old_label_alias_provenance: str,
) -> FieldEditOutcome:
    """Set the updated fields, and keep the old name as an alias when the name changes.

    Raises ``ValueError`` for a field that cannot be edited or an empty name. A field set to the
    value it already has is not a change.
    """
    values = _new_values(models, canonical, updates)
    outcome = FieldEditOutcome()
    for name, new_value in values.items():
        current = getattr(canonical, name)
        if current == new_value:
            continue
        outcome.before[name] = to_jsonable_python(current)
        outcome.after[name] = to_jsonable_python(new_value)
        setattr(canonical, name, new_value)
    if not outcome.after:
        return outcome

    if "label" in outcome.before:
        outcome.old_label = str(outcome.before["label"])
        outcome.old_label_alias = add_alias(
            session,
            models,
            canonical_id=str(canonical.id),
            alias_text=outcome.old_label,
            provenance=old_label_alias_provenance,
        )
    touch_canonical(canonical)
    session.add(canonical)
    return outcome
