"""The aliases route: add, restore and suppress names, with trusted provenance and a ledger."""

from __future__ import annotations

import pytest
from backfield_db import StylebookActivity, StylebookCleanupAction
from backfield_entities.cleanup.entity_models import cleanup_entity_models
from backfield_entities.entities.location.catalog_provenance import (
    is_location_alias_trusted_for_link_checks,
)
from backfield_entities.entities.organization.catalog_provenance import (
    is_organization_catalog_editorial_provenance,
)
from backfield_entities.entities.person.catalog_provenance import (
    is_person_alias_trusted_for_link_checks,
)
from sqlmodel import select

from tests.core_api.cleanup_fixtures import CLEANUP_BASE, create_cleanup_key, seed_entity

API_PROVENANCE = "stylebook_cleanup_api"


@pytest.fixture
def apply_headers(cleanup_client, cleanup_world) -> dict[str, str]:
    return create_cleanup_key(cleanup_client, credential_type="service", scopes=["cleanup:apply"])


def _open_run(client, headers) -> str:
    response = client.post(f"{CLEANUP_BASE}/runs", headers=headers, json={})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _post(client, headers, run_id, items, *, entity="locations", dry_run=False):
    return client.post(
        f"{CLEANUP_BASE}/{entity}/aliases",
        headers=headers,
        json={"run_id": run_id, "dry_run": dry_run, "items": items},
    )


def _item(item_id, canonical_id, action, alias_text, **extra) -> dict:
    return {
        "item_id": item_id,
        "canonical_id": canonical_id,
        "action": action,
        "alias_text": alias_text,
        **extra,
    }


def _seed(session, world, entity="locations", label="Springfield", aliases=()):
    return seed_entity(
        session,
        entity,
        stylebook_id=world.stylebook_id,
        project_id=world.project_id,
        label=label,
        aliases=aliases,
    )


def _alias_rows(session, entity, canonical_id):
    models = cleanup_entity_models(entity)
    column = models.column(models.alias, models.alias_canonical_column)
    session.expire_all()
    return list(session.exec(select(models.alias).where(column == canonical_id)).all())


@pytest.mark.parametrize(
    ("entity", "label", "new_alias"),
    [
        ("locations", "Springfield", "Springfld"),
        ("people", "Jane Doe", "J. Doe"),
        ("organizations", "Springfield Parks Department", "Parks Dept"),
    ],
)
def test_adding_an_alias_writes_trusted_rows_and_the_ledger(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, entity, label, new_alias
) -> None:
    record = _seed(cleanup_session, cleanup_world, entity, label)
    run_id = _open_run(cleanup_client, apply_headers)

    response = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [_item("a1", record.canonical_id, "add", new_alias, provenance={"by": "reader"})],
        entity=entity,
    )

    result = response.json()["items"][0]
    assert result["status"] == "applied", response.text
    assert result["summary"]["rows_changed"] >= 1
    rows = _alias_rows(cleanup_session, entity, record.canonical_id)
    added = [r for r in rows if r.alias_text == new_alias]
    assert added
    assert {r.provenance for r in added} == {API_PROVENANCE}
    assert not any(r.suppressed for r in added)

    action = cleanup_session.exec(select(StylebookCleanupAction)).one()
    assert (action.operation, action.client_item_id) == ("alias", "a1")
    assert action.before_state_json["created_alias_ids"]
    assert action.provenance_json == {"by": "reader"}
    activity = cleanup_session.exec(select(StylebookActivity)).all()
    assert [(a.source, a.event_type) for a in activity] == [("cleanup_api", "canonical_updated")]


def test_every_entity_kind_trusts_the_cleanup_api_provenance() -> None:
    assert is_location_alias_trusted_for_link_checks(API_PROVENANCE)
    assert is_person_alias_trusted_for_link_checks(API_PROVENANCE)
    assert is_organization_catalog_editorial_provenance(API_PROVENANCE)


def test_add_defaults_to_a_dry_run_and_repeats_are_noops(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    place = _seed(cleanup_session, cleanup_world)
    run_id = _open_run(cleanup_client, apply_headers)
    item = _item("a1", place.canonical_id, "add", "Springfld")

    dry = cleanup_client.post(
        f"{CLEANUP_BASE}/locations/aliases",
        headers=apply_headers,
        json={"run_id": run_id, "items": [item]},
    ).json()["items"][0]
    before = len(_alias_rows(cleanup_session, "locations", place.canonical_id))
    _post(cleanup_client, apply_headers, run_id, [item])
    repeat = _post(cleanup_client, apply_headers, run_id, [{**item, "item_id": "a2"}]).json()[
        "items"
    ][0]

    assert dry["status"] == "would_apply"
    assert before == 0
    assert (repeat["status"], repeat["reason"]) == ("noop", "already_present")
    assert len(cleanup_session.exec(select(StylebookCleanupAction)).all()) == 1


def test_suppressing_hides_the_alias_and_adding_brings_it_back(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    place = _seed(cleanup_session, cleanup_world, aliases=("Springfld",))
    run_id = _open_run(cleanup_client, apply_headers)

    suppressed = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [_item("s1", place.canonical_id, "suppress", "springfld")],
    ).json()["items"][0]
    again = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [_item("s2", place.canonical_id, "suppress", "Springfld")],
    ).json()["items"][0]

    assert suppressed["status"] == "applied"
    assert (again["status"], again["reason"]) == ("noop", "already_suppressed")
    rows = _alias_rows(cleanup_session, "locations", place.canonical_id)
    assert [(r.alias_text, r.suppressed) for r in rows] == [("Springfld", True)]
    action = cleanup_session.exec(
        select(StylebookCleanupAction).where(StylebookCleanupAction.client_item_id == "s1")
    ).one()
    assert action.before_state_json["rows_before"][0]["suppressed"] is False

    restored = _post(
        cleanup_client, apply_headers, run_id, [_item("r1", place.canonical_id, "add", "Springfld")]
    ).json()["items"][0]

    assert restored["status"] == "applied"
    rows = _alias_rows(cleanup_session, "locations", place.canonical_id)
    assert [r.suppressed for r in rows if r.alias_text == "Springfld"] == [False]
    restore_action = cleanup_session.exec(
        select(StylebookCleanupAction).where(StylebookCleanupAction.client_item_id == "r1")
    ).one()
    assert restore_action.before_state_json["rows_before"][0]["suppressed"] is True


def test_bad_items_fail_on_their_own(
    cleanup_client, cleanup_world, cleanup_session, apply_headers
) -> None:
    place = _seed(cleanup_session, cleanup_world, aliases=("Springfld",))
    other = _seed(cleanup_session, cleanup_world, label="Shelbyville")
    run_id = _open_run(cleanup_client, apply_headers)

    items = _post(
        cleanup_client,
        apply_headers,
        run_id,
        [
            _item("a", "ghost", "add", "X"),
            _item("b", place.canonical_id, "suppress", "Not an alias"),
            _item("c", place.canonical_id, "suppress", "springfield"),
            _item("d", other.canonical_id, "add", "Shelby"),
        ],
    ).json()["items"]

    assert [(i["status"], i["reason"]) for i in items] == [
        ("error", "not_found"),
        ("error", "not_found"),
        ("error", "guard_refused"),
        ("applied", None),
    ]


def test_aliases_respect_scope_run_state_and_ceiling(
    cleanup_client, cleanup_world, cleanup_session, apply_headers, monkeypatch
) -> None:
    place = _seed(cleanup_session, cleanup_world)
    read_headers = create_cleanup_key(cleanup_client)
    run_id = _open_run(cleanup_client, apply_headers)
    item = _item("a", place.canonical_id, "add", "Springfld")

    denied = _post(cleanup_client, read_headers, run_id, [item])
    unknown_run = _post(cleanup_client, apply_headers, "nope", [item])
    monkeypatch.setenv("BACKFIELD_CLEANUP_CEILING_ALIAS", "0")
    capped = _post(cleanup_client, apply_headers, run_id, [item]).json()
    monkeypatch.delenv("BACKFIELD_CLEANUP_CEILING_ALIAS")
    cleanup_client.post(
        f"{CLEANUP_BASE}/runs/{run_id}/close", headers=apply_headers, json={"status": "closed"}
    )
    closed = _post(cleanup_client, apply_headers, run_id, [item]).json()

    assert denied.status_code == 403
    assert unknown_run.status_code == 404
    assert capped["items"][0]["reason"] == "ceiling_reached"
    assert closed["items"][0]["reason"] == "run_not_open"
