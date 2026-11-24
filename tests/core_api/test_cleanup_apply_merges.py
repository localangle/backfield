"""Cleanup runs, the merges route, the ledger, and `merged_into` resolution."""

from __future__ import annotations

import pytest
from backfield_db import (
    StylebookActivity,
    StylebookCanonicalRedirect,
    StylebookCleanupAction,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from sqlmodel import Session, select

from tests.core_api.cleanup_fixtures import (
    CLEANUP_BASE,
    create_cleanup_key,
    seed_entity,
)


@pytest.fixture
def apply_headers(cleanup_client, cleanup_world) -> dict[str, str]:
    return create_cleanup_key(cleanup_client, credential_type="service", scopes=["cleanup:apply"])


@pytest.fixture
def reindex_calls(monkeypatch) -> list[tuple[int, str, int]]:
    calls: list[tuple[int, str, int]] = []

    def record(session, *, project_id, entity_type, entity_id) -> None:
        calls.append((project_id, entity_type, entity_id))

    monkeypatch.setattr(
        "core_api.routers.public.cleanup.merges.enqueue_semantic_reindex_for_entity", record
    )
    return calls


def _open_run(client, headers, **body) -> str:
    response = client.post(f"{CLEANUP_BASE}/runs", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _merge(client, headers, run_id, items, *, dry_run=False, entity="locations"):
    return client.post(
        f"{CLEANUP_BASE}/{entity}/merges",
        headers=headers,
        json={"run_id": run_id, "dry_run": dry_run, "items": items},
    )


def _item(item_id: str, source: str, target: str, **extra) -> dict:
    return {"item_id": item_id, "source_id": source, "target_id": target, **extra}


def _two_places(session, world, *, source="Springfield", target="Springfield, USA"):
    left = seed_entity(
        session,
        "locations",
        stylebook_id=world.stylebook_id,
        project_id=world.project_id,
        label=source,
        kind="city",
        aliases=("Springfld",),
    )
    right = seed_entity(
        session,
        "locations",
        stylebook_id=world.stylebook_id,
        project_id=world.project_id,
        label=target,
        kind="city",
    )
    return left, right


def test_runs_need_the_apply_scope_to_open_but_only_read_to_look(
    cleanup_client, cleanup_world
) -> None:
    apply_headers = create_cleanup_key(
        cleanup_client, credential_type="service", scopes=["cleanup:apply"]
    )
    read_headers = create_cleanup_key(cleanup_client)

    denied = cleanup_client.post(f"{CLEANUP_BASE}/runs", headers=read_headers, json={})
    run_id = _open_run(
        cleanup_client, apply_headers, label="2024 places", client_run_ref="local-run-7"
    )

    assert denied.status_code == 403
    fetched = cleanup_client.get(f"{CLEANUP_BASE}/runs/{run_id}", headers=read_headers).json()
    assert fetched["status"] == "open"
    assert fetched["label"] == "2024 places"
    assert fetched["client_run_ref"] == "local-run-7"
    assert fetched["credential_label"]
    listed = cleanup_client.get(f"{CLEANUP_BASE}/runs", headers=read_headers).json()
    assert [r["id"] for r in listed["items"]] == [run_id]
    missing = cleanup_client.get(f"{CLEANUP_BASE}/runs/nope", headers=read_headers)
    assert missing.status_code == 404


def test_closing_a_run(cleanup_client, apply_headers) -> None:
    run_id = _open_run(cleanup_client, apply_headers)
    url = f"{CLEANUP_BASE}/runs/{run_id}/close"

    closed = cleanup_client.post(url, headers=apply_headers, json={"status": "closed"})
    again = cleanup_client.post(url, headers=apply_headers, json={"status": "closed"})
    switched = cleanup_client.post(url, headers=apply_headers, json={"status": "aborted"})

    assert closed.json()["status"] == "closed"
    assert closed.json()["closed_at"] is not None
    assert again.status_code == 200
    assert switched.status_code == 409
    assert (
        cleanup_client.post(
            f"{CLEANUP_BASE}/runs/nope/close", headers=apply_headers, json={}
        ).status_code
        == 404
    )


def test_merge_defaults_to_a_dry_run_that_changes_nothing(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, reindex_calls
) -> None:
    left, right = _two_places(cleanup_session, cleanup_world)
    run_id = _open_run(cleanup_client, apply_headers)

    response = cleanup_client.post(
        f"{CLEANUP_BASE}/locations/merges",
        headers=apply_headers,
        json={"run_id": run_id, "items": [_item("a", left.canonical_id, right.canonical_id)]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dry_run"] is True
    assert body["counts"] == {"would_apply": 1, "applied": 0, "noop": 0, "error": 0}, body
    assert body["items"][0]["summary"]["relinked_count"] == 1
    assert body["items"][0]["action_id"] is None
    cleanup_session.expire_all()
    assert cleanup_session.get(StylebookLocationCanonical, left.canonical_id) is not None
    assert cleanup_session.exec(select(StylebookCleanupAction)).all() == []
    assert cleanup_session.exec(select(StylebookCanonicalRedirect)).all() == []
    assert reindex_calls == []


def test_applied_merge_is_recorded_everywhere(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, reindex_calls
) -> None:
    left, right = _two_places(cleanup_session, cleanup_world)
    run_id = _open_run(cleanup_client, apply_headers)
    provenance = {"reason": "same_place", "reader": "consensus"}

    response = _merge(
        cleanup_client,
        apply_headers,
        run_id,
        [_item("item-1", left.canonical_id, right.canonical_id, provenance=provenance)],
    )

    result = response.json()["items"][0]
    assert result["status"] == "applied", response.text
    assert result["reindex_queued"] is True
    assert result["summary"]["source_label"] == "Springfield"
    assert result["summary"]["transferred_alias_count"] >= 1
    assert reindex_calls == [(cleanup_world.project_id, "location", left.substrate_id)]

    cleanup_session.expire_all()
    assert cleanup_session.get(StylebookLocationCanonical, left.canonical_id) is None
    linked = cleanup_session.get(SubstrateLocation, left.substrate_id)
    assert linked.stylebook_location_canonical_id == right.canonical_id
    aliases = {
        a.normalized_alias
        for a in cleanup_session.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == right.canonical_id
            )
        )
    }
    assert {"springfld", "springfield"} <= aliases

    action = cleanup_session.exec(select(StylebookCleanupAction)).one()
    assert action.id == result["action_id"]
    assert (action.run_id, action.operation, action.entity_type) == (run_id, "merge", "location")
    assert (action.canonical_id, action.related_canonical_id) == (
        left.canonical_id,
        right.canonical_id,
    )
    assert action.client_item_id == "item-1"
    assert action.provenance_json == provenance
    assert action.credential_label
    assert action.reindex_queued is True
    before = action.before_state_json
    assert before["schema_version"] == 1
    assert before["source"]["canonical"]["label"] == "Springfield"
    assert [a["alias_text"] for a in before["source"]["aliases"]] == ["Springfld"]
    assert before["source"]["linked_records"] == [[cleanup_world.project_id, left.substrate_id]]
    assert before["target"]["canonical"]["id"] == right.canonical_id
    assert "geometry" not in before["source"]["canonical"]

    redirect = cleanup_session.exec(select(StylebookCanonicalRedirect)).one()
    assert (redirect.old_id, redirect.new_id, redirect.action_id) == (
        left.canonical_id,
        right.canonical_id,
        action.id,
    )
    activity = cleanup_session.exec(
        select(StylebookActivity).where(StylebookActivity.event_type == "cleanup_merge")
    ).one()
    assert activity.actor_type == "agent"
    assert activity.source == "cleanup_api"
    assert activity.payload_json["run_id"] == run_id
    assert activity.payload_json["client_item_id"] == "item-1"
    assert activity.payload_json["provenance"] == provenance


def test_ledger_reads_show_what_was_applied(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, reindex_calls
) -> None:
    left, right = _two_places(cleanup_session, cleanup_world)
    run_id = _open_run(cleanup_client, apply_headers)
    applied = _merge(
        cleanup_client, apply_headers, run_id, [_item("one", left.canonical_id, right.canonical_id)]
    ).json()["items"][0]
    read_headers = create_cleanup_key(cleanup_client)

    run = cleanup_client.get(f"{CLEANUP_BASE}/runs/{run_id}", headers=read_headers).json()
    actions = cleanup_client.get(
        f"{CLEANUP_BASE}/runs/{run_id}/actions", headers=read_headers
    ).json()
    one = cleanup_client.get(
        f"{CLEANUP_BASE}/actions/{applied['action_id']}", headers=read_headers
    ).json()

    assert run["action_counts"] == {"merge": 1}
    assert [a["client_item_id"] for a in actions["items"]] == ["one"]
    assert actions["items"][0]["before_state"] is None
    assert one["before_state"]["source"]["canonical"]["label"] == "Springfield"
    assert (
        cleanup_client.get(f"{CLEANUP_BASE}/actions/nope", headers=read_headers).status_code == 404
    )
    assert (
        cleanup_client.get(f"{CLEANUP_BASE}/runs/nope/actions", headers=read_headers).status_code
        == 404
    )


def test_repeating_a_merge_is_a_noop(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, reindex_calls
) -> None:
    left, right = _two_places(cleanup_session, cleanup_world)
    run_id = _open_run(cleanup_client, apply_headers)
    items = [_item("one", left.canonical_id, right.canonical_id)]
    _merge(cleanup_client, apply_headers, run_id, items)

    again = _merge(cleanup_client, apply_headers, run_id, items).json()["items"][0]

    assert (again["status"], again["reason"]) == ("noop", "already_merged")
    cleanup_session.expire_all()
    assert len(cleanup_session.exec(select(StylebookCleanupAction)).all()) == 1


def test_resolution_follows_merges_across_a_chain(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, reindex_calls
) -> None:
    first, second = _two_places(cleanup_session, cleanup_world)
    third = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Springfield, Illinois",
        kind="city",
    )
    run_id = _open_run(cleanup_client, apply_headers)
    _merge(
        cleanup_client, apply_headers, run_id, [_item("1", first.canonical_id, second.canonical_id)]
    )
    _merge(
        cleanup_client, apply_headers, run_id, [_item("2", second.canonical_id, third.canonical_id)]
    )
    read_headers = create_cleanup_key(cleanup_client)

    old = cleanup_client.get(
        f"{CLEANUP_BASE}/locations/{first.canonical_id}/resolution", headers=read_headers
    ).json()
    live = cleanup_client.get(
        f"{CLEANUP_BASE}/locations/{third.canonical_id}/resolution", headers=read_headers
    ).json()

    assert old == {
        "entity_type": "location",
        "requested_id": first.canonical_id,
        "resolved_id": third.canonical_id,
        "merged": True,
        "deleted": False,
    }
    assert live["merged"] is False
    assert live["resolved_id"] == third.canonical_id
    # The first redirect now points straight at the final survivor.
    cleanup_session.expire_all()
    direct = cleanup_session.exec(
        select(StylebookCanonicalRedirect).where(
            StylebookCanonicalRedirect.old_id == first.canonical_id
        )
    ).one()
    assert direct.new_id == third.canonical_id


def test_a_merge_the_guard_refuses_changes_nothing_and_does_not_stop_other_items(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, reindex_calls
) -> None:
    mismatched = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Springfield Park",
        kind="park",
    )
    left, right = _two_places(cleanup_session, cleanup_world)
    run_id = _open_run(cleanup_client, apply_headers)

    response = _merge(
        cleanup_client,
        apply_headers,
        run_id,
        [
            _item("bad", mismatched.canonical_id, right.canonical_id),
            _item("good", left.canonical_id, right.canonical_id),
        ],
    )

    bad, good = response.json()["items"]
    assert (bad["status"], bad["reason"]) == ("error", "guard_refused")
    assert "different kinds of places" in bad["message"]
    assert good["status"] == "applied"
    cleanup_session.expire_all()
    assert cleanup_session.get(StylebookLocationCanonical, mismatched.canonical_id) is not None
    assert response.json()["counts"] == {"would_apply": 0, "applied": 1, "noop": 0, "error": 1}


def test_unknown_and_identical_canonicals_are_reported(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, reindex_calls
) -> None:
    left, _ = _two_places(cleanup_session, cleanup_world)
    run_id = _open_run(cleanup_client, apply_headers)

    items = _merge(
        cleanup_client,
        apply_headers,
        run_id,
        [
            _item("same", left.canonical_id, left.canonical_id),
            _item("no-source", "missing", left.canonical_id),
            _item("no-target", left.canonical_id, "missing"),
        ],
    ).json()["items"]

    assert [(i["status"], i["reason"]) for i in items] == [
        ("error", "same_canonical"),
        ("error", "not_found"),
        ("error", "not_found"),
    ]


def test_an_unknown_run_is_a_404(cleanup_client, cleanup_world, apply_headers) -> None:
    response = _merge(cleanup_client, apply_headers, "nope", [_item("a", "x", "y")])
    assert response.status_code == 404


def test_closed_and_aborted_runs_refuse_applies(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, reindex_calls
) -> None:
    left, right = _two_places(cleanup_session, cleanup_world)
    run_id = _open_run(cleanup_client, apply_headers)
    cleanup_client.post(
        f"{CLEANUP_BASE}/runs/{run_id}/close", headers=apply_headers, json={"status": "aborted"}
    )

    result = _merge(
        cleanup_client, apply_headers, run_id, [_item("a", left.canonical_id, right.canonical_id)]
    ).json()["items"][0]

    assert (result["status"], result["reason"]) == ("error", "run_not_open")
    cleanup_session.expire_all()
    assert cleanup_session.get(StylebookLocationCanonical, left.canonical_id) is not None


def test_the_run_ceiling_stops_further_merges(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, reindex_calls, monkeypatch
) -> None:
    monkeypatch.setenv("BACKFIELD_CLEANUP_CEILING_MERGE", "1")
    first, second = _two_places(cleanup_session, cleanup_world)
    third = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Springfield, Illinois",
        kind="city",
    )
    run_id = _open_run(cleanup_client, apply_headers)

    items = _merge(
        cleanup_client,
        apply_headers,
        run_id,
        [
            _item("1", first.canonical_id, third.canonical_id),
            _item("2", second.canonical_id, third.canonical_id),
        ],
    ).json()["items"]
    dry = _merge(
        cleanup_client,
        apply_headers,
        run_id,
        [_item("3", second.canonical_id, third.canonical_id)],
        dry_run=True,
    ).json()["items"][0]

    assert [i["status"] for i in items] == ["applied", "error"]
    assert items[1]["reason"] == "ceiling_reached"
    assert dry["reason"] == "ceiling_reached"
    cleanup_session.expire_all()
    assert cleanup_session.get(StylebookLocationCanonical, second.canonical_id) is not None


def test_a_ledger_failure_undoes_the_merge(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, reindex_calls, monkeypatch
) -> None:
    def failing_record(*args, **kwargs):
        raise RuntimeError("ledger down")

    monkeypatch.setattr("backfield_entities.cleanup.merge_items.record_action", failing_record)
    left, right = _two_places(cleanup_session, cleanup_world)
    run_id = _open_run(cleanup_client, apply_headers)

    result = _merge(
        cleanup_client, apply_headers, run_id, [_item("a", left.canonical_id, right.canonical_id)]
    ).json()["items"][0]

    assert (result["status"], result["reason"]) == ("error", "ledger_failed")
    cleanup_session.expire_all()
    assert cleanup_session.get(StylebookLocationCanonical, left.canonical_id) is not None
    assert cleanup_session.exec(select(StylebookCanonicalRedirect)).all() == []
    linked = cleanup_session.get(SubstrateLocation, left.substrate_id)
    assert linked.stylebook_location_canonical_id == left.canonical_id


def test_people_and_organizations_merge_through_the_same_route(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, reindex_calls
) -> None:
    run_id = _open_run(cleanup_client, apply_headers)
    for entity, singular, source, target in (
        ("people", "person", "Jane Q. Public", "Jane Public"),
        ("organizations", "organization", "City Council", "Springfield City Council"),
    ):
        left = seed_entity(
            cleanup_session,
            entity,
            stylebook_id=cleanup_world.stylebook_id,
            project_id=cleanup_world.project_id,
            label=source,
        )
        right = seed_entity(
            cleanup_session,
            entity,
            stylebook_id=cleanup_world.stylebook_id,
            project_id=cleanup_world.project_id,
            label=target,
        )

        item = _merge(
            cleanup_client,
            apply_headers,
            run_id,
            [_item(entity, left.canonical_id, right.canonical_id)],
            entity=entity,
        ).json()["items"][0]

        assert item["status"] == "applied", item
        cleanup_session.expire_all()
        action = cleanup_session.exec(
            select(StylebookCleanupAction).where(StylebookCleanupAction.entity_type == singular)
        ).one()
        assert action.before_state_json["entity_type"] == singular
        resolved = cleanup_client.get(
            f"{CLEANUP_BASE}/{entity}/{left.canonical_id}/resolution", headers=apply_headers
        ).json()
        assert resolved["resolved_id"] == right.canonical_id


def test_capabilities_list_merges_only_for_keys_that_can_apply(
    cleanup_client, cleanup_world, apply_headers
) -> None:
    read_headers = create_cleanup_key(cleanup_client)

    apply_caps = cleanup_client.get(f"{CLEANUP_BASE}/capabilities", headers=apply_headers).json()
    read_caps = cleanup_client.get(f"{CLEANUP_BASE}/capabilities", headers=read_headers).json()

    assert apply_caps["operations"] == [
        "merges",
        "dismissals",
        "aliases",
        "edits",
        "retirements",
        "deletions",
        "decisions",
    ]
    assert read_caps["operations"] == []
    assert apply_caps["limits"]["run_ceilings"]["merge"] == 5000
    assert apply_caps["limits"]["run_ceilings"]["deletion"] == 200
    assert apply_caps["limits"]["apply_items_max"] == 100


def test_the_ui_merge_path_also_records_where_the_old_id_went(
    cleanup_world, cleanup_session
) -> None:
    from backfield_entities.cleanup.apply_merge import MergeRequest, apply_merge

    left, right = _two_places(cleanup_session, cleanup_world)

    apply_merge(
        cleanup_session,
        MergeRequest(
            entity_type="location",
            stylebook_id=cleanup_world.stylebook_id,
            organization_id=cleanup_world.organization_id,
            source_canonical_id=left.canonical_id,
            target_canonical_id=right.canonical_id,
        ),
        reindex=None,
    )
    cleanup_session.commit()

    redirect = cleanup_session.exec(select(StylebookCanonicalRedirect)).one()
    assert (redirect.old_id, redirect.new_id, redirect.action_id) == (
        left.canonical_id,
        right.canonical_id,
        None,
    )
    assert isinstance(cleanup_session, Session)


def test_ceiling_settings_fall_back_to_defaults_when_unusable(monkeypatch) -> None:
    from backfield_entities.cleanup.ceilings import ceiling_for

    assert ceiling_for("deletion") == 200
    monkeypatch.setenv("BACKFIELD_CLEANUP_CEILING_DELETION", "12")
    assert ceiling_for("deletion") == 12
    monkeypatch.setenv("BACKFIELD_CLEANUP_CEILING_DELETION", "0")
    assert ceiling_for("deletion") == 0
    for unusable in ("-3", "many"):
        monkeypatch.setenv("BACKFIELD_CLEANUP_CEILING_DELETION", unusable)
        assert ceiling_for("deletion") == 200
