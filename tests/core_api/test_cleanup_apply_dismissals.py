"""The dismissals route: set check results aside, or bring them back, with reasons and a ledger."""

from __future__ import annotations

import pytest
from backfield_db import StylebookActivity, StylebookCleanupAction, StylebookCleanupDismissal
from sqlmodel import select

from tests.core_api.cleanup_fixtures import CLEANUP_BASE, create_cleanup_key, seed_entity


@pytest.fixture
def apply_headers(cleanup_client, cleanup_world) -> dict[str, str]:
    return create_cleanup_key(cleanup_client, credential_type="service", scopes=["cleanup:apply"])


def _open_run(client, headers) -> str:
    response = client.post(f"{CLEANUP_BASE}/runs", headers=headers, json={})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _post(client, headers, run_id, items, *, dry_run=False):
    return client.post(
        f"{CLEANUP_BASE}/dismissals",
        headers=headers,
        json={"run_id": run_id, "dry_run": dry_run, "items": items},
    )


def _two_places(session, world):
    return [
        seed_entity(
            session,
            "locations",
            stylebook_id=world.stylebook_id,
            project_id=world.project_id,
            label=label,
            kind="city",
        )
        for label in ("Springfield", "Springfield, USA")
    ]


def _pair_item(item_id: str, left, right, **extra) -> dict:
    return {
        "item_id": item_id,
        "check_id": "duplicate-locations",
        "left_id": left.canonical_id,
        "right_id": right.canonical_id,
        **extra,
    }


def test_dismissing_a_pair_records_the_reason_run_and_ledger(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    left, right = _two_places(cleanup_session, cleanup_world)
    run_id = _open_run(cleanup_client, apply_headers)

    response = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [
            _pair_item(
                "p1", left, right, reason_code="different_places", provenance={"by": "reader"}
            )
        ],
    )

    result = response.json()["items"][0]
    assert result["status"] == "applied", response.text
    assert result["summary"]["canonical_ids"] == sorted([left.canonical_id, right.canonical_id])
    cleanup_session.expire_all()
    row = cleanup_session.exec(select(StylebookCleanupDismissal)).one()
    assert (row.reason_code, row.run_id) == ("different_places", run_id)
    action = cleanup_session.exec(select(StylebookCleanupAction)).one()
    assert (action.operation, action.entity_type, action.client_item_id) == (
        "dismissal",
        "location",
        "p1",
    )
    assert action.before_state_json["existing"] is None
    activity = cleanup_session.exec(select(StylebookActivity)).all()
    assert [(a.actor_type, a.source, a.event_type) for a in activity] == [
        ("agent", "cleanup_api", "cleanup_keep_separate")
    ]

    listed = cleanup_client.get(f"{CLEANUP_BASE}/dismissals", headers=apply_headers).json()
    item = listed["items"][0]
    assert (item["reason_code"], item["run_id"]) == ("different_places", run_id)
    assert item["credential_label"]


def test_dismiss_defaults_to_a_dry_run_and_repeats_are_noops(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    left, right = _two_places(cleanup_session, cleanup_world)
    run_id = _open_run(cleanup_client, apply_headers)

    dry = cleanup_client.post(
        f"{CLEANUP_BASE}/dismissals",
        headers=apply_headers,
        json={"run_id": run_id, "items": [_pair_item("p1", left, right)]},
    ).json()
    cleanup_session.expire_all()
    assert dry["items"][0]["status"] == "would_apply"
    assert cleanup_session.exec(select(StylebookCleanupDismissal)).all() == []

    _post(cleanup_client, apply_headers, run_id, [_pair_item("p1", left, right)])
    again = _post(cleanup_client, apply_headers, run_id, [_pair_item("p2", right, left)]).json()

    assert again["items"][0]["status"] == "noop"
    assert again["items"][0]["reason"] == "already_dismissed"
    cleanup_session.expire_all()
    assert len(cleanup_session.exec(select(StylebookCleanupAction)).all()) == 1


def test_reopening_deletes_the_row_and_keeps_history_in_the_ledger(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    left, right = _two_places(cleanup_session, cleanup_world)
    run_id = _open_run(cleanup_client, apply_headers)
    _post(cleanup_client, apply_headers, run_id, [_pair_item("p1", left, right, reason_code="x")])
    reopen = {**_pair_item("r1", left, right), "action": "reopen"}

    missing = _post(
        cleanup_client, apply_headers, run_id, [{**reopen, "right_id": left.canonical_id}]
    ).json()["items"][0]
    result = _post(cleanup_client, apply_headers, run_id, [reopen]).json()["items"][0]
    repeat = _post(cleanup_client, apply_headers, run_id, [reopen]).json()["items"][0]

    assert missing["reason"] == "same_canonical"
    assert result["status"] == "applied"
    assert (repeat["status"], repeat["reason"]) == ("noop", "not_dismissed")
    cleanup_session.expire_all()
    assert cleanup_session.exec(select(StylebookCleanupDismissal)).all() == []
    reopened = cleanup_session.exec(
        select(StylebookCleanupAction).where(StylebookCleanupAction.client_item_id == "r1")
    ).one()
    assert reopened.before_state_json["existing"]["reason_code"] == "x"
    events = [a.event_type for a in cleanup_session.exec(select(StylebookActivity))]
    assert events == ["cleanup_keep_separate", "cleanup_reopen"]


def test_list_checks_dismiss_a_single_canonical(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    place, _ = _two_places(cleanup_session, cleanup_world)
    run_id = _open_run(cleanup_client, apply_headers)

    result = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [
            {
                "item_id": "g1",
                "check_id": "missing-geometry-locations",
                "canonical_id": place.canonical_id,
            }
        ],
    ).json()["items"][0]

    assert result["status"] == "applied"
    cleanup_session.expire_all()
    row = cleanup_session.exec(select(StylebookCleanupDismissal)).one()
    assert place.canonical_id in row.pair_key
    assert cleanup_session.exec(select(StylebookActivity)).one().event_type == "cleanup_keep"


def test_bad_items_fail_on_their_own(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    left, right = _two_places(cleanup_session, cleanup_world)
    run_id = _open_run(cleanup_client, apply_headers)

    items = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [
            {"item_id": "a", "check_id": "nope", "canonical_id": left.canonical_id},
            {"item_id": "b", "check_id": "duplicate-locations", "canonical_id": left.canonical_id},
            {
                "item_id": "c",
                "check_id": "missing-geometry-locations",
                "left_id": left.canonical_id,
                "right_id": right.canonical_id,
            },
            {
                "item_id": "d",
                "check_id": "duplicate-locations",
                "left_id": left.canonical_id,
                "right_id": "ghost",
            },
            _pair_item("e", left, right),
        ],
    ).json()["items"]

    assert [(i["status"], i["reason"]) for i in items] == [
        ("error", "unknown_check"),
        ("error", "invalid_item"),
        ("error", "invalid_item"),
        ("error", "not_found"),
        ("applied", None),
    ]


def test_dismissals_respect_scope_run_state_and_ceiling(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, monkeypatch
) -> None:
    left, right = _two_places(cleanup_session, cleanup_world)
    read_headers = create_cleanup_key(cleanup_client)
    run_id = _open_run(cleanup_client, apply_headers)

    denied = _post(cleanup_client, read_headers, run_id, [_pair_item("p", left, right)])
    unknown_run = _post(cleanup_client, apply_headers, "nope", [_pair_item("p", left, right)])
    monkeypatch.setenv("BACKFIELD_CLEANUP_CEILING_DISMISSAL", "0")
    capped = _post(cleanup_client, apply_headers, run_id, [_pair_item("p", left, right)]).json()
    monkeypatch.delenv("BACKFIELD_CLEANUP_CEILING_DISMISSAL")
    cleanup_client.post(
        f"{CLEANUP_BASE}/runs/{run_id}/close", headers=apply_headers, json={"status": "closed"}
    )
    closed = _post(cleanup_client, apply_headers, run_id, [_pair_item("p", left, right)]).json()

    assert denied.status_code == 403
    assert unknown_run.status_code == 404
    assert capped["items"][0]["reason"] == "ceiling_reached"
    assert closed["items"][0]["reason"] == "run_not_open"
