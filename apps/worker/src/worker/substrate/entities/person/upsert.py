"""Substrate person upserts for worker persistence."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from backfield_db import SubstratePerson
from backfield_entities.entities.person.review import (
    entry_people_bucket as _entry_people_bucket,
)
from backfield_entities.entities.person.review import (
    finalize_review_fields_from_entry,
    surname_inferred_from_relative,
)
from backfield_entities.entities.person.types import (
    derive_person_sort_key,
    normalize_person_type,
    person_identity_fingerprint,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from worker.substrate.common import _normalize_name, _utcnow


@dataclass(frozen=True)
class PersonUpsertResult:
    person: SubstratePerson
    created: bool
    updated: bool


def _people_bucket_for_entry(entry: dict[str, Any]) -> str:
    return _entry_people_bucket(entry)


def _display_name_for_person_entry(entry: dict[str, Any]) -> str:
    name = entry.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return ""


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _person_type_from_entry(entry: dict[str, Any]) -> str | None:
    return normalize_person_type(_optional_text(entry.get("type")))


def _iter_people_entries(people: list[Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for item in people:
        if isinstance(item, dict):
            yield _people_bucket_for_entry(item), item


def _fetch_substrate_person_after_unique_violation(
    session: Session,
    *,
    project_id: int,
    identity_fingerprint: str,
) -> SubstratePerson | None:
    return session.exec(
        select(SubstratePerson).where(
            SubstratePerson.project_id == project_id,
            SubstratePerson.identity_fingerprint == identity_fingerprint,
        )
    ).first()


def _sort_key_from_entry(entry: dict[str, Any], display_name: str) -> str | None:
    explicit = _optional_text(entry.get("sort_key"))
    return derive_person_sort_key(display_name, explicit=explicit)


def _apply_substrate_person_merge(
    person: SubstratePerson,
    *,
    display_name: str,
    normalized: str,
    title: str | None,
    affiliation: str | None,
    public_figure: bool,
    person_type: str | None,
    sort_key: str | None,
    status: str,
    fingerprint: str,
    details: dict[str, Any],
) -> None:
    now = _utcnow()
    person.name = display_name
    person.normalized_name = normalized
    person.title = title
    person.affiliation = affiliation
    person.public_figure = public_figure
    person.person_type = person_type or person.person_type
    person.sort_key = sort_key
    person.status = status
    person.identity_fingerprint = fingerprint
    person.source_kind = "person_extract"
    prev_details = (
        person.source_details_json if isinstance(person.source_details_json, dict) else {}
    )
    person.source_details_json = {**prev_details, **details}
    person.updated_at = now


def _upsert_person(
    session: Session,
    *,
    project_id: int,
    bucket: str,
    entry: dict[str, Any],
    run_id: str,
    graph_id: str,
    update_existing: bool = True,
) -> PersonUpsertResult | None:
    display_name = _display_name_for_person_entry(entry)
    normalized = _normalize_name(display_name)
    if not normalized:
        return None

    title = _optional_text(entry.get("title"))
    affiliation = _optional_text(entry.get("affiliation"))
    public_figure = bool(entry.get("public_figure"))
    person_type = _person_type_from_entry(entry)
    sort_key = _sort_key_from_entry(entry, display_name)
    fingerprint = person_identity_fingerprint(
        normalized_name=normalized,
        affiliation=affiliation,
    )

    status = "needs_review" if bucket == "needs_review" else "provisional"
    review_fields = finalize_review_fields_from_entry(entry)
    details = {
        "graph_id": graph_id,
        "run_id": run_id,
        "people_bucket": bucket,
        **{
            k: review_fields[k]
            for k in ("review_handling", "review_reason_code", "review_message")
            if review_fields.get(k) is not None
        },
    }
    if surname_inferred_from_relative(entry):
        details["surname_inferred_from_relative"] = True
    raw_entry_id = entry.get("id") or entry.get("mention_id")
    if raw_entry_id is not None and str(raw_entry_id).strip():
        details["raw_entry_id"] = str(raw_entry_id).strip()

    person = session.exec(
        select(SubstratePerson).where(
            SubstratePerson.project_id == project_id,
            SubstratePerson.identity_fingerprint == fingerprint,
        )
    ).first()

    if person is None:
        new_person = SubstratePerson(
            project_id=project_id,
            name=display_name,
            normalized_name=normalized,
            title=title,
            affiliation=affiliation,
            public_figure=public_figure,
            person_type=person_type,
            sort_key=sort_key,
            status=status,
            identity_fingerprint=fingerprint,
            source_kind="person_extract",
            source_details_json=details,
        )
        try:
            with session.begin_nested():
                session.add(new_person)
                session.flush()
        except IntegrityError as exc:
            person = _fetch_substrate_person_after_unique_violation(
                session,
                project_id=project_id,
                identity_fingerprint=fingerprint,
            )
            if person is None:
                raise RuntimeError(
                    "substrate_person insert collided on unique key but concurrent row "
                    "was not visible; retry the persistence step"
                ) from exc
            _apply_substrate_person_merge(
                person,
                display_name=display_name,
                normalized=normalized,
                title=title,
                affiliation=affiliation,
                public_figure=public_figure,
                person_type=person_type,
                sort_key=sort_key,
                status=status,
                fingerprint=fingerprint,
                details=details,
            )
            session.add(person)
            session.flush()
        else:
            person = new_person
        return PersonUpsertResult(person=person, created=True, updated=False)

    if not update_existing:
        return PersonUpsertResult(person=person, created=False, updated=False)

    _apply_substrate_person_merge(
        person,
        display_name=display_name,
        normalized=normalized,
        title=title,
        affiliation=affiliation,
        public_figure=public_figure,
        person_type=person_type,
        sort_key=sort_key,
        status=status,
        fingerprint=fingerprint,
        details=details,
    )
    session.add(person)
    session.flush()
    return PersonUpsertResult(person=person, created=False, updated=True)
