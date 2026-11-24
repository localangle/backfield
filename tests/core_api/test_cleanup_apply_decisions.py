"""The candidate decisions route: link, create and defer, the same for all three entity kinds."""

from __future__ import annotations

import pytest
from backfield_db import StylebookActivity, StylebookCleanupAction
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED, CANONICAL_LINK_WAIVED
from backfield_entities.cleanup.entity_models import cleanup_entity_models
from sqlmodel import select

from tests.core_api.cleanup_fixtures import (
    CLEANUP_BASE,
    create_cleanup_key,
    seed_entity,
    seed_substrate,
)

# (entity, candidate kind, a different kind to create with)
ENTITIES = [
    ("locations", "city", "county"),
    ("people", "individual", "public_official"),
    ("organizations", "media", "government"),
]


@pytest.fixture
def apply_headers(cleanup_client, cleanup_world) -> dict[str, str]:
    return create_cleanup_key(cleanup_client, credential_type="service", scopes=["cleanup:apply"])


@pytest.fixture
def reindex_calls(monkeypatch) -> list[tuple[int, str, int]]:
    calls: list[tuple[int, str, int]] = []

    def record(session, *, project_id, entity_type, entity_id) -> None:
        calls.append((project_id, entity_type, entity_id))

    monkeypatch.setattr(
        "core_api.routers.public.cleanup.decisions.enqueue_semantic_reindex_for_entity", record
    )
    return calls


def _open_run(client, headers) -> str:
    response = client.post(f"{CLEANUP_BASE}/runs", headers=headers, json={})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _decide(client, headers, run_id, items, *, entity="locations", dry_run=False):
    return client.post(
        f"{CLEANUP_BASE}/candidates/{entity}/decisions",
        headers=headers,
        json={"run_id": run_id, "dry_run": dry_run, "items": items},
    )


def _item(item_id, candidate_id, action, **extra) -> dict:
    return {"item_id": item_id, "candidate_id": candidate_id, "action": action, **extra}


def _candidate(
    session, world, entity, name, *, kind=None, project_id=None, link_status="pending"
) -> int:
    return seed_substrate(
        session,
        entity,
        canonical_id=None,
        project_id=project_id or world.project_id,
        name=name,
        kind=kind,
        link_status=link_status,
    )


def _row(session, entity, row_id):
    session.expire_all()
    return session.get(cleanup_entity_models(entity).substrate, row_id)


def _link_of(entity, row) -> str | None:
    return getattr(row, cleanup_entity_models(entity).substrate_canonical_column)


def _only_result(response) -> dict:
    assert response.status_code == 200, response.text
    return response.json()["items"][0]


@pytest.mark.parametrize(("entity", "kind", "_other"), ENTITIES)
def test_linking_a_candidate_attaches_it_and_is_recorded(
    cleanup_client,
    cleanup_world,
    cleanup_session,
    apply_headers,
    reindex_calls,
    entity,
    kind,
    _other,
) -> None:
    target = seed_entity(
        cleanup_session,
        entity,
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Springfield Original",
        kind=kind,
        aliases=("Springfield Original",),
    )
    candidate_id = _candidate(
        cleanup_session, cleanup_world, entity, "Springfield Variant", kind=kind
    )
    run_id = _open_run(cleanup_client, apply_headers)
    item = _item("l1", candidate_id, "link", canonical_id=target.canonical_id)

    dry = _only_result(
        _decide(cleanup_client, apply_headers, run_id, [item], entity=entity, dry_run=True)
    )
    assert dry["status"] == "would_apply", dry
    assert _link_of(entity, _row(cleanup_session, entity, candidate_id)) is None
    assert reindex_calls == []

    result = _only_result(_decide(cleanup_client, apply_headers, run_id, [item], entity=entity))

    assert result["status"] == "applied", result
    assert result["summary"]["canonical_id"] == target.canonical_id
    assert result["summary"]["created"] is False
    assert result["reindex_queued"] is True
    models = cleanup_entity_models(entity)
    assert reindex_calls == [(cleanup_world.project_id, models.singular, candidate_id)]
    row = _row(cleanup_session, entity, candidate_id)
    assert _link_of(entity, row) == target.canonical_id
    assert row.canonical_link_status == CANONICAL_LINK_LINKED
    assert row.canonical_review_reasons_json == [
        {"code": "linked_manual_accept_existing", "canonical_id": target.canonical_id}
    ]
    alias_column = getattr(models.alias, models.alias_canonical_column)
    aliases = cleanup_session.exec(
        select(models.alias.normalized_alias).where(alias_column == target.canonical_id)
    ).all()
    assert "springfield variant" in aliases
    action = cleanup_session.exec(select(StylebookCleanupAction)).one()
    assert (action.operation, action.client_item_id, action.canonical_id) == (
        "decision",
        "l1",
        target.canonical_id,
    )
    assert action.before_state_json["candidate"]["canonical_link_status"] == "pending"
    assert "springfield original" in action.before_state_json["target_alias_norms"]
    events = cleanup_session.exec(select(StylebookActivity)).all()
    assert [(e.source, e.event_type, e.entity_id) for e in events] == [
        ("cleanup_api", "substrate_linked", target.canonical_id)
    ]

    again = _only_result(_decide(cleanup_client, apply_headers, run_id, [item], entity=entity))
    assert (again["status"], again["reason"]) == ("noop", "already_linked")


@pytest.mark.parametrize(("entity", "kind", "other_kind"), ENTITIES)
def test_creating_a_record_from_a_candidate(
    cleanup_client,
    cleanup_world,
    cleanup_session,
    apply_headers,
    reindex_calls,
    entity,
    kind,
    other_kind,
) -> None:
    candidate_id = _candidate(cleanup_session, cleanup_world, entity, "Brand New Thing", kind=kind)
    run_id = _open_run(cleanup_client, apply_headers)
    item = _item("c1", candidate_id, "create", name="Brand New Place", kind=other_kind)

    result = _only_result(_decide(cleanup_client, apply_headers, run_id, [item], entity=entity))

    assert result["status"] == "applied", result
    summary = result["summary"]
    assert (summary["created"], summary["canonical_label"]) == (True, "Brand New Place")
    models = cleanup_entity_models(entity)
    canonical = cleanup_session.get(models.canonical, summary["canonical_id"])
    assert canonical is not None
    assert (int(canonical.stylebook_id), canonical.status) == (cleanup_world.stylebook_id, "active")
    assert models.canonical_kind(canonical) == other_kind
    row = _row(cleanup_session, entity, candidate_id)
    assert _link_of(entity, row) == summary["canonical_id"]
    assert row.canonical_link_status == CANONICAL_LINK_LINKED
    assert row.canonical_review_reasons_json == [
        {"code": "linked_manual_accept_create_new", "canonical_id": summary["canonical_id"]}
    ]
    assert reindex_calls == [(cleanup_world.project_id, models.singular, candidate_id)]
    events = [e.event_type for e in cleanup_session.exec(select(StylebookActivity))]
    assert "canonical_created" in events

    again = _only_result(_decide(cleanup_client, apply_headers, run_id, [item], entity=entity))
    assert (again["status"], again["reason"]) == ("noop", "already_linked")
    assert len(cleanup_session.exec(select(models.canonical)).all()) == 1


def test_creating_defaults_to_the_candidates_own_name(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    candidate_id = _candidate(
        cleanup_session, cleanup_world, "people", "Jane Doe", kind="individual"
    )
    run_id = _open_run(cleanup_client, apply_headers)

    result = _only_result(
        _decide(
            cleanup_client,
            apply_headers,
            run_id,
            [_item("c1", candidate_id, "create")],
            entity="people",
        )
    )

    assert result["summary"]["canonical_label"] == "Jane Doe"


@pytest.mark.parametrize(("entity", "kind", "_other"), ENTITIES)
def test_deferring_moves_a_candidate_to_the_deferred_queue(
    cleanup_client,
    cleanup_world,
    cleanup_session,
    apply_headers,
    reindex_calls,
    entity,
    kind,
    _other,
) -> None:
    candidate_id = _candidate(cleanup_session, cleanup_world, entity, "Unclear Thing", kind=kind)
    run_id = _open_run(cleanup_client, apply_headers)
    item = _item("d1", candidate_id, "defer")

    result = _only_result(_decide(cleanup_client, apply_headers, run_id, [item], entity=entity))

    assert result["status"] == "applied", result
    assert result["summary"]["canonical_id"] is None
    assert result["reindex_queued"] is False
    assert reindex_calls == []
    row = _row(cleanup_session, entity, candidate_id)
    assert row.canonical_link_status == CANONICAL_LINK_WAIVED
    assert row.canonical_review_reasons_json == [
        {"code": "deferred_manual", "provenance": "stylebook_cleanup_api"}
    ]
    action = cleanup_client.get(
        f"{CLEANUP_BASE}/actions/{result['action_id']}", headers=apply_headers
    )
    assert action.status_code == 200
    assert action.json()["canonical_id"] is None
    deferred = cleanup_client.get(
        f"{CLEANUP_BASE}/candidates/{entity}?status=deferred", headers=apply_headers
    ).json()
    assert [c["id"] for c in deferred["items"]] == [candidate_id]

    again = _only_result(_decide(cleanup_client, apply_headers, run_id, [item], entity=entity))
    assert (again["status"], again["reason"]) == ("noop", "already_deferred")


def test_a_deferred_candidate_can_still_be_linked_or_created(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    target = seed_entity(
        cleanup_session,
        "organizations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Acme Corporation",
    )
    first = _candidate(
        cleanup_session, cleanup_world, "organizations", "Acme Corp", link_status="waived"
    )
    second = _candidate(
        cleanup_session, cleanup_world, "organizations", "Other Org", link_status="waived"
    )
    run_id = _open_run(cleanup_client, apply_headers)

    items = _decide(
        cleanup_client,
        apply_headers,
        run_id,
        [
            _item("a", first, "link", canonical_id=target.canonical_id),
            _item("b", second, "create"),
        ],
        entity="organizations",
    ).json()["items"]

    assert [i["status"] for i in items] == ["applied", "applied"]


def test_candidates_from_any_project_in_the_stylebook_can_be_decided(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    candidate_id = _candidate(
        cleanup_session,
        cleanup_world,
        "locations",
        "Elsewhere",
        project_id=cleanup_world.second_project_id,
    )
    run_id = _open_run(cleanup_client, apply_headers)

    result = _only_result(
        _decide(cleanup_client, apply_headers, run_id, [_item("c", candidate_id, "create")])
    )

    assert result["status"] == "applied"


def test_refusals_are_reported_per_item_and_change_nothing(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    models = cleanup_entity_models("locations")
    live = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Live Place",
    )
    retired = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Retired Place",
    )
    canonical = cleanup_session.get(models.canonical, retired.canonical_id)
    canonical.status = "inactive"
    cleanup_session.add(canonical)
    cleanup_session.commit()
    candidate_id = _candidate(cleanup_session, cleanup_world, "locations", "Candidate Place")
    run_id = _open_run(cleanup_client, apply_headers)
    cases = [
        (
            "retired",
            _item("1", candidate_id, "link", canonical_id=retired.canonical_id),
            "guard_refused",
        ),
        ("unknown record", _item("2", candidate_id, "link", canonical_id="nope"), "not_found"),
        ("unknown candidate", _item("3", 999999, "defer"), "not_found"),
        ("already linked", _item("4", live.substrate_id, "defer"), "guard_refused"),
        ("link without a target", _item("5", candidate_id, "link"), "invalid_item"),
        (
            "create with a target",
            _item("6", candidate_id, "create", canonical_id="x"),
            "invalid_item",
        ),
        ("defer with a name", _item("7", candidate_id, "defer", name="x"), "invalid_item"),
        ("bad place kind", _item("8", candidate_id, "create", kind="not-a-kind"), "invalid_item"),
        ("blank name", _item("9", candidate_id, "create", name="  "), "invalid_item"),
    ]

    results = _decide(
        cleanup_client, apply_headers, run_id, [item for _label, item, _reason in cases]
    ).json()["items"]

    for (label, _item_body, reason), result in zip(cases, results, strict=True):
        assert (result["status"], result["reason"]) == ("error", reason), label
    row = _row(cleanup_session, "locations", candidate_id)
    assert _link_of("locations", row) is None
    assert row.canonical_link_status == "pending"
    assert cleanup_session.exec(select(StylebookCleanupAction)).all() == []


def test_geometry_only_applies_to_locations(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    candidate_id = _candidate(cleanup_session, cleanup_world, "people", "Jane Doe")
    run_id = _open_run(cleanup_client, apply_headers)

    result = _only_result(
        _decide(
            cleanup_client,
            apply_headers,
            run_id,
            [_item("g", candidate_id, "create", geometry={"type": "Point", "coordinates": [0, 0]})],
            entity="people",
        )
    )

    assert (result["status"], result["reason"]) == ("error", "invalid_item")


def test_decisions_respect_scope_run_state_and_ceiling(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, monkeypatch
) -> None:
    candidate_id = _candidate(cleanup_session, cleanup_world, "locations", "Candidate Place")
    read_headers = create_cleanup_key(cleanup_client)
    run_id = _open_run(cleanup_client, apply_headers)
    item = _item("a", candidate_id, "defer")

    denied = _decide(cleanup_client, read_headers, run_id, [item])
    unknown_run = _decide(cleanup_client, apply_headers, "nope", [item])
    monkeypatch.setenv("BACKFIELD_CLEANUP_CEILING_DECISION", "0")
    capped = _decide(cleanup_client, apply_headers, run_id, [item]).json()
    monkeypatch.delenv("BACKFIELD_CLEANUP_CEILING_DECISION")
    cleanup_client.post(
        f"{CLEANUP_BASE}/runs/{run_id}/close", headers=apply_headers, json={"status": "closed"}
    )
    closed = _decide(cleanup_client, apply_headers, run_id, [item]).json()

    assert denied.status_code == 403
    assert unknown_run.status_code == 404
    assert capped["items"][0]["reason"] == "ceiling_reached"
    assert closed["items"][0]["reason"] == "run_not_open"
