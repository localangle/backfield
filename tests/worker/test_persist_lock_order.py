"""Lock strength, lock ordering, and geocode-cache race handling for substrate persistence."""

from __future__ import annotations

from typing import Any

import pytest
from backfield_db import (
    AgateRun,
    SubstrateLocation,
    SubstrateLocationCache,
    SubstrateOrganization,
    SubstratePerson,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, col, create_engine, select
from worker.substrate import persist_from_consolidated
from worker.substrate.entities.location import upsert as location_upsert
from worker.substrate.entities.lock_order import _ordered_lock_statement

from tests.worker.test_organization_substrate_persistence import _sample_organization_entry
from tests.worker.test_person_substrate_persistence import _sample_person_entry
from tests.worker.test_substrate_persistence import _bootstrap_project, _city_places


def _postgres_sql(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def _cache_upsert_kwargs(*, project_id: int, formatted_address: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "query_text": "Chicago, IL",
        "location_type": "city",
        "entry": {"location": "Chicago, IL"},
        "geocode_type": "pelias",
        "geocode_result": {"id": "pelias:chicago"},
        "geometry_json": None,
        "geometry_value": None,
        "geometry_type_str": None,
        "formatted_address": formatted_address,
        "h3_cell": None,
        "h3_resolution": None,
    }


def test_ordered_lock_statement_is_ordered_no_key_update_and_project_scoped() -> None:
    statement = _ordered_lock_statement(
        col(SubstratePerson.id),
        col(SubstratePerson.project_id) == 7,
        col(SubstratePerson.identity_fingerprint).in_(["a", "b"]),
    )
    sql = _postgres_sql(statement)
    assert "ORDER BY substrate_person.id" in sql
    assert sql.rstrip().endswith("FOR NO KEY UPDATE")
    assert "substrate_person.project_id =" in sql


def test_location_row_locks_use_no_key_update() -> None:
    statement = (
        select(SubstrateLocation)
        .where(col(SubstrateLocation.id) == 1)
        .with_for_update(key_share=True)
    )
    assert _postgres_sql(statement).rstrip().endswith("FOR NO KEY UPDATE")


def test_location_cache_insert_race_falls_back_to_update(monkeypatch) -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-cache", project_slug="proj-cache")
        location_upsert._upsert_location_cache(
            session, **_cache_upsert_kwargs(project_id=project_id, formatted_address="Old")
        )
        session.commit()

        # Simulate losing the race: the first lookup sees no row although one now exists.
        real_select = location_upsert._select_location_cache_row_for_update
        calls = {"count": 0}

        def _first_lookup_misses(*args: Any, **kwargs: Any) -> SubstrateLocationCache | None:
            calls["count"] += 1
            return None if calls["count"] == 1 else real_select(*args, **kwargs)

        monkeypatch.setattr(
            location_upsert, "_select_location_cache_row_for_update", _first_lookup_misses
        )
        location_upsert._upsert_location_cache(
            session, **_cache_upsert_kwargs(project_id=project_id, formatted_address="New")
        )
        session.commit()

        rows = session.exec(select(SubstrateLocationCache)).all()
        assert len(rows) == 1
        assert rows[0].formatted_address == "New"
        assert calls["count"] == 2


def test_location_cache_insert_race_reraises_when_conflicting_row_is_not_found(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-cache2", project_slug="proj-cache2")
        location_upsert._upsert_location_cache(
            session, **_cache_upsert_kwargs(project_id=project_id, formatted_address="Old")
        )
        session.commit()
        monkeypatch.setattr(
            location_upsert, "_select_location_cache_row_for_update", lambda *a, **k: None
        )
        with pytest.raises(IntegrityError):
            location_upsert._upsert_location_cache(
                session, **_cache_upsert_kwargs(project_id=project_id, formatted_address="New")
            )


def test_handlers_prelock_existing_rows_by_identity(monkeypatch) -> None:
    import worker.substrate.entities.location.handler as location_handler
    import worker.substrate.entities.organization.handler as organization_handler
    import worker.substrate.entities.person.handler as person_handler

    recorded: dict[str, Any] = {}

    def _recorder(name: str, **extra: str) -> Any:
        def _record(session: Session, **kwargs: Any) -> None:
            recorded[name] = {key: sorted(kwargs[arg]) for key, arg in extra.items()} | {
                "project_id": kwargs["project_id"]
            }

        return _record

    monkeypatch.setattr(person_handler, "lock_person_rows", _recorder("person", f="fingerprints"))
    monkeypatch.setattr(
        organization_handler, "lock_organization_rows", _recorder("org", f="fingerprints")
    )
    monkeypatch.setattr(
        location_handler,
        "lock_location_rows",
        _recorder("location", f="fingerprints", e="external_identities"),
    )

    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-lock", project_slug="proj-lock")
        session.add(AgateRun(id="run-lock", graph_id="graph-lock", status="pending"))
        session.commit()
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-lock",
            run_id="run-lock",
            consolidated={
                "text": "Mayor Jane Smith and Chicago City Hall spoke in Chicago.",
                "url": "https://example.com/lock",
                "places": _city_places(),
                "people": [_sample_person_entry()],
                "organizations": [_sample_organization_entry()],
            },
            db_output_params={"auto_apply_canonicalization": False},
        )
        session.commit()

        person = session.exec(select(SubstratePerson)).one()
        organization = session.exec(select(SubstrateOrganization)).one()
        location = session.exec(select(SubstrateLocation)).one()

    assert recorded["person"]["f"] == [person.identity_fingerprint]
    assert recorded["org"]["f"] == [organization.identity_fingerprint]
    assert recorded["location"]["f"] == [location.identity_fingerprint]
    assert recorded["location"]["e"] == [(location.external_source, location.external_id)]
    assert recorded["person"]["project_id"] == project_id
