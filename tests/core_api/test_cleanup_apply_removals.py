"""The retirements and deletions routes: release linked records, ledger, and the same rules for
locations, people and organizations."""

from __future__ import annotations

import pytest
from backfield_db import (
    StylebookActivity,
    StylebookCleanupAction,
    StylebookConnection,
)
from backfield_entities.cleanup.entity_models import cleanup_entity_models
from sqlmodel import select

from tests.core_api.cleanup_fixtures import CLEANUP_BASE, create_cleanup_key, seed_entity

ENTITIES = [
    ("locations", "Springfield"),
    ("people", "Jane Doe"),
    ("organizations", "Acme Corporation"),
]


@pytest.fixture
def apply_headers(cleanup_client, cleanup_world) -> dict[str, str]:
    return create_cleanup_key(cleanup_client, credential_type="service", scopes=["cleanup:apply"])


@pytest.fixture
def reindex_calls(monkeypatch) -> list[tuple[int, str, int]]:
    calls: list[tuple[int, str, int]] = []

    def record(session, *, project_id, entity_type, entity_id) -> None:
        calls.append((project_id, entity_type, entity_id))

    for module in ("retirements", "deletions"):
        monkeypatch.setattr(
            f"core_api.routers.public.cleanup.{module}.enqueue_semantic_reindex_for_entity", record
        )
    return calls


def _open_run(client, headers) -> str:
    response = client.post(f"{CLEANUP_BASE}/runs", headers=headers, json={})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _post(client, headers, route, run_id, items, *, entity="locations", dry_run=False):
    return client.post(
        f"{CLEANUP_BASE}/{entity}/{route}",
        headers=headers,
        json={"run_id": run_id, "dry_run": dry_run, "items": items},
    )


def _item(item_id, canonical_id, **extra) -> dict:
    return {"item_id": item_id, "canonical_id": canonical_id, **extra}


def _seed(session, world, entity, label):
    return seed_entity(
        session,
        entity,
        stylebook_id=world.stylebook_id,
        project_id=world.project_id,
        label=label,
    )


def _canonical(session, entity, canonical_id):
    session.expire_all()
    return session.get(cleanup_entity_models(entity).canonical, canonical_id)


def _record(session, entity, record_id):
    session.expire_all()
    return session.get(cleanup_entity_models(entity).substrate, record_id)


@pytest.mark.parametrize(("entity", "label"), ENTITIES)
def test_retiring_with_linked_records_is_refused_by_default(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, entity, label
) -> None:
    seeded = _seed(cleanup_session, cleanup_world, entity, label)
    run_id = _open_run(cleanup_client, apply_headers)

    result = _post(
        cleanup_client,
        apply_headers,
        "retirements",
        run_id,
        [_item("r1", seeded.canonical_id)],
        entity=entity,
    ).json()["items"][0]

    assert (result["status"], result["reason"]) == ("error", "linked_records_present")
    assert _canonical(cleanup_session, entity, seeded.canonical_id).status == "active"


@pytest.mark.parametrize(("entity", "label"), ENTITIES)
def test_retiring_releases_linked_records_and_is_recorded(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, reindex_calls, entity, label
) -> None:
    seeded = _seed(cleanup_session, cleanup_world, entity, label)
    run_id = _open_run(cleanup_client, apply_headers)
    item = _item(
        "r1",
        seeded.canonical_id,
        mention_disposition="requeue",
        mention_reason_code="not_a_real_one",
        provenance={"by": "reader"},
    )

    dry = _post(
        cleanup_client, apply_headers, "retirements", run_id, [item], entity=entity, dry_run=True
    ).json()["items"][0]
    assert dry["status"] == "would_apply"
    assert _canonical(cleanup_session, entity, seeded.canonical_id).status == "active"
    assert reindex_calls == []

    result = _post(
        cleanup_client, apply_headers, "retirements", run_id, [item], entity=entity
    ).json()["items"][0]

    assert result["status"] == "applied", result
    assert result["summary"]["released_record_count"] == 1
    assert result["reindex_queued"] is True
    assert reindex_calls == [
        (cleanup_world.project_id, cleanup_entity_models(entity).singular, seeded.substrate_id)
    ]
    assert _canonical(cleanup_session, entity, seeded.canonical_id).status == "inactive"
    released = _record(cleanup_session, entity, seeded.substrate_id)
    models = cleanup_entity_models(entity)
    assert getattr(released, models.substrate_canonical_column) is None
    assert released.canonical_link_status == "pending"
    assert released.canonical_review_reasons_json == [
        {"code": "not_a_real_one", "retired_canonical_id": seeded.canonical_id}
    ]
    action = cleanup_session.exec(select(StylebookCleanupAction)).one()
    assert (action.operation, action.client_item_id) == ("retirement", "r1")
    assert action.before_state_json["canonical"]["canonical"]["status"] == "active"
    assert action.before_state_json["released_records"][0]["canonical_link_status"] == "linked"
    events = cleanup_session.exec(select(StylebookActivity)).all()
    assert [(e.source, e.event_type) for e in events] == [("cleanup_api", "canonical_retired")]

    again = _post(
        cleanup_client, apply_headers, "retirements", run_id, [item], entity=entity
    ).json()["items"][0]
    assert (again["status"], again["reason"]) == ("noop", "already_inactive")


def test_retiring_without_linked_records_needs_no_disposition_and_closes_connections(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    place = _seed(cleanup_session, cleanup_world, "locations", "Springfield")
    cleanup_session.delete(_record(cleanup_session, "locations", place.substrate_id))
    cleanup_session.add(
        StylebookConnection(
            project_id=cleanup_world.project_id,
            stylebook_id=cleanup_world.stylebook_id,
            from_entity_type="location",
            from_entity_id=place.canonical_id,
            to_entity_type="organization",
            to_entity_id="someone",
        )
    )
    cleanup_session.commit()
    run_id = _open_run(cleanup_client, apply_headers)

    result = _post(
        cleanup_client, apply_headers, "retirements", run_id, [_item("r1", place.canonical_id)]
    ).json()["items"][0]

    assert result["status"] == "applied", result
    assert result["summary"]["connections_closed"] == 1
    cleanup_session.expire_all()
    assert cleanup_session.exec(select(StylebookConnection)).one().closed_at is not None


def test_waiving_marks_released_records_as_not_needing_a_record(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    place = _seed(cleanup_session, cleanup_world, "locations", "Springfield")
    run_id = _open_run(cleanup_client, apply_headers)

    result = _post(
        cleanup_client,
        apply_headers,
        "retirements",
        run_id,
        [_item("r1", place.canonical_id, mention_disposition="waive")],
    ).json()["items"][0]

    assert result["status"] == "applied"
    released = _record(cleanup_session, "locations", place.substrate_id)
    assert released.canonical_link_status == "waived"
    assert (
        released.canonical_review_reasons_json[0]["code"] == "reset_pending_after_canonical_retired"
    )


@pytest.mark.parametrize(("entity", "label"), ENTITIES)
def test_reinstating_brings_a_retired_record_back(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, entity, label
) -> None:
    seeded = _seed(cleanup_session, cleanup_world, entity, label)
    canonical = _canonical(cleanup_session, entity, seeded.canonical_id)
    canonical.status = "inactive"
    cleanup_session.add(canonical)
    cleanup_session.commit()
    run_id = _open_run(cleanup_client, apply_headers)
    item = _item("b1", seeded.canonical_id, action="reinstate")

    result = _post(
        cleanup_client, apply_headers, "retirements", run_id, [item], entity=entity
    ).json()["items"][0]
    again = _post(
        cleanup_client, apply_headers, "retirements", run_id, [item], entity=entity
    ).json()["items"][0]

    assert result["status"] == "applied", result
    assert _canonical(cleanup_session, entity, seeded.canonical_id).status == "active"
    assert (again["status"], again["reason"]) == ("noop", "already_active")
    events = cleanup_session.exec(select(StylebookActivity)).all()
    assert [e.event_type for e in events] == ["canonical_reinstated"]


@pytest.mark.parametrize(("entity", "label"), ENTITIES)
def test_deleting_requeues_records_and_keeps_a_full_snapshot(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, reindex_calls, entity, label
) -> None:
    seeded = _seed(cleanup_session, cleanup_world, entity, label)
    models = cleanup_entity_models(entity)
    cleanup_session.add(
        models.alias(
            **{models.alias_canonical_column: seeded.canonical_id},
            alias_text="Known As",
            normalized_alias="known as",
            provenance="ingest",
        )
    )
    cleanup_session.commit()
    run_id = _open_run(cleanup_client, apply_headers)
    refused = _post(
        cleanup_client,
        apply_headers,
        "deletions",
        run_id,
        [_item("d0", seeded.canonical_id)],
        entity=entity,
    ).json()["items"][0]
    item = _item("d1", seeded.canonical_id, mention_disposition="requeue")

    result = _post(
        cleanup_client, apply_headers, "deletions", run_id, [item], entity=entity
    ).json()["items"][0]

    assert (refused["status"], refused["reason"]) == ("error", "linked_records_present")
    assert result["status"] == "applied", result
    assert result["reindex_queued"] is True
    assert reindex_calls == [(cleanup_world.project_id, models.singular, seeded.substrate_id)]
    assert _canonical(cleanup_session, entity, seeded.canonical_id) is None
    released = _record(cleanup_session, entity, seeded.substrate_id)
    assert released.canonical_link_status == "pending"
    assert released.canonical_review_reasons_json == [
        {
            "code": "reset_pending_after_canonical_deleted",
            "deleted_canonical_id": seeded.canonical_id,
        }
    ]
    action = cleanup_session.exec(
        select(StylebookCleanupAction).where(StylebookCleanupAction.client_item_id == "d1")
    ).one()
    snapshot = action.before_state_json["canonical"]
    assert snapshot["canonical"]["label"] == label
    assert [a["alias_text"] for a in snapshot["aliases"]] == ["Known As"]
    assert snapshot["linked_records"] == [[cleanup_world.project_id, seeded.substrate_id]]
    events = [e.event_type for e in cleanup_session.exec(select(StylebookActivity))]
    assert events == ["canonical_deleted"]

    again = _post(cleanup_client, apply_headers, "deletions", run_id, [item], entity=entity).json()[
        "items"
    ][0]
    assert (again["status"], again["reason"]) == ("noop", "already_deleted")
    resolution = cleanup_client.get(
        f"{CLEANUP_BASE}/{entity}/{seeded.canonical_id}/resolution", headers=apply_headers
    ).json()
    assert (resolution["merged"], resolution["deleted"]) == (False, True)


def test_deleting_with_nothing_linked_works_and_unknown_ids_are_not_found(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, reindex_calls
) -> None:
    place = _seed(cleanup_session, cleanup_world, "locations", "Springfield")
    cleanup_session.delete(_record(cleanup_session, "locations", place.substrate_id))
    cleanup_session.commit()
    run_id = _open_run(cleanup_client, apply_headers)

    items = _post(
        cleanup_client,
        apply_headers,
        "deletions",
        run_id,
        [_item("d1", place.canonical_id), _item("d2", "ghost")],
    ).json()["items"]

    assert [(i["status"], i["reason"]) for i in items] == [
        ("applied", None),
        ("error", "not_found"),
    ]
    assert items[0]["reindex_queued"] is False
    assert reindex_calls == []
    unknown = cleanup_client.get(
        f"{CLEANUP_BASE}/locations/ghost/resolution", headers=apply_headers
    ).json()
    assert unknown["deleted"] is False


@pytest.mark.parametrize(
    ("route", "ceiling"), [("retirements", "RETIREMENT"), ("deletions", "DELETION")]
)
def test_removals_respect_scope_run_state_and_ceiling(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, monkeypatch, route, ceiling
) -> None:
    place = _seed(cleanup_session, cleanup_world, "locations", "Springfield")
    read_headers = create_cleanup_key(cleanup_client)
    run_id = _open_run(cleanup_client, apply_headers)
    item = _item("a", place.canonical_id, mention_disposition="requeue")

    denied = _post(cleanup_client, read_headers, route, run_id, [item])
    unknown_run = _post(cleanup_client, apply_headers, route, "nope", [item])
    monkeypatch.setenv(f"BACKFIELD_CLEANUP_CEILING_{ceiling}", "0")
    capped = _post(cleanup_client, apply_headers, route, run_id, [item]).json()
    monkeypatch.delenv(f"BACKFIELD_CLEANUP_CEILING_{ceiling}")
    cleanup_client.post(
        f"{CLEANUP_BASE}/runs/{run_id}/close", headers=apply_headers, json={"status": "closed"}
    )
    closed = _post(cleanup_client, apply_headers, route, run_id, [item]).json()

    assert denied.status_code == 403
    assert unknown_run.status_code == 404
    assert capped["items"][0]["reason"] == "ceiling_reached"
    assert closed["items"][0]["reason"] == "run_not_open"
