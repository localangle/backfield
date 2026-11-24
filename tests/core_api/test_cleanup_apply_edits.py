"""The edits route: field changes, rename-keeps-alias, geography, saved places, and the ledger."""

from __future__ import annotations

import pytest
from backfield_db import (
    StylebookActivity,
    StylebookCleanupAction,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from sqlmodel import select

from tests.core_api.cleanup_fixtures import CLEANUP_BASE, create_cleanup_key, seed_entity

POINT = {"type": "Point", "coordinates": [-89.65, 39.78]}
OTHER_POINT = {"type": "Point", "coordinates": [-90.0, 40.0]}


@pytest.fixture
def apply_headers(cleanup_client, cleanup_world) -> dict[str, str]:
    return create_cleanup_key(cleanup_client, credential_type="service", scopes=["cleanup:apply"])


def _open_run(client, headers) -> str:
    response = client.post(f"{CLEANUP_BASE}/runs", headers=headers, json={})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _post(client, headers, run_id, items, *, entity="locations", dry_run=False):
    return client.post(
        f"{CLEANUP_BASE}/{entity}/edits",
        headers=headers,
        json={"run_id": run_id, "dry_run": dry_run, "items": items},
    )


def _item(item_id, canonical_id, changes=None, **extra) -> dict:
    return {"item_id": item_id, "canonical_id": canonical_id, "changes": changes or {}, **extra}


def _seed(session, world, entity="locations", label="Springfield", kind=None):
    return seed_entity(
        session,
        entity,
        stylebook_id=world.stylebook_id,
        project_id=world.project_id,
        label=label,
        kind=kind,
    )


def test_editing_fields_records_before_and_after(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    place = _seed(cleanup_session, cleanup_world, kind="city")
    run_id = _open_run(cleanup_client, apply_headers)

    response = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [
            _item(
                "e1",
                place.canonical_id,
                {"location_type": " Town ", "formatted_address": "Springfield, IL"},
                provenance={"by": "reader"},
            )
        ],
    )

    result = response.json()["items"][0]
    assert result["status"] == "applied", response.text
    assert result["summary"]["changed_fields"] == ["formatted_address", "location_type"]
    assert result["summary"]["before"] == {"location_type": "city", "formatted_address": None}
    assert result["summary"]["after"] == {
        "location_type": "town",
        "formatted_address": "Springfield, IL",
    }
    cleanup_session.expire_all()
    row = cleanup_session.get(StylebookLocationCanonical, place.canonical_id)
    assert (row.location_type, row.formatted_address) == ("town", "Springfield, IL")
    action = cleanup_session.exec(select(StylebookCleanupAction)).one()
    assert (action.operation, action.client_item_id) == ("edit", "e1")
    assert action.before_state_json["fields"] == {
        "location_type": "city",
        "formatted_address": None,
    }
    activity = cleanup_session.exec(select(StylebookActivity)).all()
    assert [(a.source, a.event_type) for a in activity] == [("cleanup_api", "canonical_updated")]


def test_edit_defaults_to_a_dry_run_and_matching_values_are_a_noop(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    place = _seed(cleanup_session, cleanup_world, kind="city")
    run_id = _open_run(cleanup_client, apply_headers)

    dry = cleanup_client.post(
        f"{CLEANUP_BASE}/locations/edits",
        headers=apply_headers,
        json={
            "run_id": run_id,
            "items": [_item("e1", place.canonical_id, {"location_type": "county"})],
        },
    ).json()["items"][0]
    same = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [_item("e2", place.canonical_id, {"location_type": "city"})],
    ).json()["items"][0]

    assert dry["status"] == "would_apply"
    assert (same["status"], same["reason"]) == ("noop", "no_change")
    cleanup_session.expire_all()
    assert (
        cleanup_session.get(StylebookLocationCanonical, place.canonical_id).location_type == "city"
    )
    assert cleanup_session.exec(select(StylebookCleanupAction)).all() == []


def test_a_rename_keeps_the_old_name_as_a_trusted_alias(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    place = _seed(cleanup_session, cleanup_world, label="Spingfield")
    run_id = _open_run(cleanup_client, apply_headers)

    result = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [_item("e1", place.canonical_id, {"label": "Springfield"})],
    ).json()["items"][0]

    assert result["status"] == "applied"
    assert result["summary"]["old_name_kept_as_alias"] is True
    cleanup_session.expire_all()
    aliases = cleanup_session.exec(
        select(StylebookLocationAlias).where(
            StylebookLocationAlias.location_canonical_id == place.canonical_id
        )
    ).all()
    assert {a.provenance for a in aliases if a.alias_text == "Spingfield"} == {
        "stylebook_cleanup_api"
    }
    action = cleanup_session.exec(select(StylebookCleanupAction)).one()
    assert action.before_state_json["fields"] == {"label": "Spingfield"}
    assert action.before_state_json["created_alias_ids"]


def test_geography_can_be_set_and_cleared_with_the_old_shape_kept(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    place = _seed(cleanup_session, cleanup_world, kind="city")
    run_id = _open_run(cleanup_client, apply_headers)

    set_result = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [_item("g1", place.canonical_id, {"geometry": POINT})],
    ).json()["items"][0]
    cleared = _post(
        cleanup_client, apply_headers, run_id, [_item("g2", place.canonical_id, {"geometry": None})]
    ).json()["items"][0]

    assert set_result["status"] == "applied"
    assert set_result["summary"]["after"]["geometry"] == POINT
    assert cleared["status"] == "applied"
    assert cleared["summary"]["before"]["geometry"] == POINT
    cleanup_session.expire_all()
    row = cleanup_session.get(StylebookLocationCanonical, place.canonical_id)
    assert (row.geometry_json, row.geometry_type, row.h3_cell) == (None, None, None)
    cleared_action = cleanup_session.exec(
        select(StylebookCleanupAction).where(StylebookCleanupAction.client_item_id == "g2")
    ).one()
    assert cleared_action.before_state_json["geometry"]["geometry_json"] == POINT
    assert cleared_action.before_state_json["geometry"]["geometry_type"] == "Point"


def test_geography_can_follow_onto_linked_saved_places(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    place = _seed(cleanup_session, cleanup_world, kind="city")
    run_id = _open_run(cleanup_client, apply_headers)

    result = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [_item("g1", place.canonical_id, {"geometry": POINT}, apply_geometry_to_saved_places=True)],
    ).json()["items"][0]

    assert result["status"] == "applied", result
    assert result["summary"]["saved_places_updated"] == [place.substrate_id]
    cleanup_session.expire_all()
    saved = cleanup_session.get(SubstrateLocation, place.substrate_id)
    assert saved.geometry_json == POINT
    action = cleanup_session.exec(select(StylebookCleanupAction)).one()
    assert action.before_state_json["saved_places"][0]["id"] == place.substrate_id
    assert action.before_state_json["saved_places"][0]["geometry_json"] is None

    again = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [_item("g2", place.canonical_id, apply_geometry_to_saved_places=True)],
    ).json()["items"][0]
    assert (again["status"], again["reason"]) == ("noop", "no_change")


def test_people_and_organizations_edit_their_own_fields(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    person = _seed(cleanup_session, cleanup_world, "people", "Jane Doe")
    org = _seed(cleanup_session, cleanup_world, "organizations", "Acme Corporation")
    run_id = _open_run(cleanup_client, apply_headers)

    person_result = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [_item("p1", person.canonical_id, {"title": " Mayor ", "public_figure": True})],
        entity="people",
    ).json()["items"][0]
    org_result = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [_item("o1", org.canonical_id, {"organization_type": "company"})],
        entity="organizations",
    ).json()["items"][0]

    assert person_result["status"] == "applied", person_result
    assert person_result["summary"]["after"] == {"title": "Mayor", "public_figure": True}
    assert org_result["status"] == "applied", org_result
    assert org_result["summary"]["after"] == {"organization_type": "company"}


def test_bad_items_fail_on_their_own(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    place = _seed(cleanup_session, cleanup_world, kind="city")
    run_id = _open_run(cleanup_client, apply_headers)

    items = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [
            _item("a", "ghost", {"label": "X"}),
            _item("b", place.canonical_id, {"status": "retired"}),
            _item("c", place.canonical_id, {"title": "Mayor"}),
            _item("d", place.canonical_id),
            _item("e", place.canonical_id, {"label": "   "}),
            _item("f", place.canonical_id, {"geometry": {"type": "Nope"}}),
            _item("g", place.canonical_id, apply_geometry_to_saved_places=True),
            _item("h", place.canonical_id, {"location_type": "county"}),
        ],
    ).json()["items"]

    assert [(i["status"], i["reason"]) for i in items] == [
        ("error", "not_found"),
        ("error", "invalid_item"),
        ("error", "invalid_item"),
        ("error", "invalid_item"),
        ("error", "guard_refused"),
        ("error", "guard_refused"),
        ("error", "invalid_item"),
        ("applied", None),
    ]
    assert "Allowed fields" in items[1]["message"]
    person_flag = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [_item("p", place.canonical_id, apply_geometry_to_saved_places=True)],
        entity="people",
    ).json()["items"][0]
    assert person_flag["reason"] == "not_found"


def test_edits_respect_scope_run_state_and_ceiling(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, monkeypatch
) -> None:
    place = _seed(cleanup_session, cleanup_world, kind="city")
    read_headers = create_cleanup_key(cleanup_client)
    run_id = _open_run(cleanup_client, apply_headers)
    item = _item("a", place.canonical_id, {"location_type": "county"})

    denied = _post(cleanup_client, read_headers, run_id, [item])
    unknown_run = _post(cleanup_client, apply_headers, "nope", [item])
    monkeypatch.setenv("BACKFIELD_CLEANUP_CEILING_EDIT", "0")
    capped = _post(cleanup_client, apply_headers, run_id, [item]).json()
    monkeypatch.delenv("BACKFIELD_CLEANUP_CEILING_EDIT")
    cleanup_client.post(
        f"{CLEANUP_BASE}/runs/{run_id}/close", headers=apply_headers, json={"status": "closed"}
    )
    closed = _post(cleanup_client, apply_headers, run_id, [item]).json()

    assert denied.status_code == 403
    assert unknown_run.status_code == 404
    assert capped["items"][0]["reason"] == "ceiling_reached"
    assert closed["items"][0]["reason"] == "run_not_open"
