"""Dismissal and integrity reads."""

from __future__ import annotations

from backfield_db import (
    StylebookCleanupDismissal,
    StylebookConnection,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED, CANONICAL_LINK_PENDING

from tests.core_api.cleanup_fixtures import (
    CLEANUP_BASE,
    create_cleanup_key,
    seed_entity,
    seed_substrate,
)


def test_dismissals_list_filter_and_page(cleanup_client, cleanup_world, cleanup_session) -> None:
    headers = create_cleanup_key(cleanup_client)
    for index, check_id in enumerate(
        ("duplicate-locations", "duplicate-locations", "mismatched-locations")
    ):
        cleanup_session.add(
            StylebookCleanupDismissal(
                stylebook_id=cleanup_world.stylebook_id,
                check_id=check_id,
                pair_key=f"a{index}|b{index}",
            )
        )
    cleanup_session.add(
        StylebookCleanupDismissal(
            stylebook_id=cleanup_world.foreign_stylebook_id,
            check_id="duplicate-locations",
            pair_key="x|y",
        )
    )
    cleanup_session.commit()
    url = f"{CLEANUP_BASE}/dismissals"

    everything = cleanup_client.get(url, headers=headers).json()
    assert len(everything["items"]) == 3
    assert everything["items"][0]["canonical_ids"] == ["a0", "b0"]

    only_dupes = cleanup_client.get(
        url, headers=headers, params={"check_id": "duplicate-locations"}
    ).json()
    assert [i["pair_key"] for i in only_dupes["items"]] == ["a0|b0", "a1|b1"]

    first = cleanup_client.get(url, headers=headers, params={"limit": 2}).json()
    second = cleanup_client.get(
        url, headers=headers, params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert [i["pair_key"] for i in second["items"]] == ["a2|b2"]
    assert second["next_cursor"] is None
    assert cleanup_client.get(url, headers=headers, params={"cursor": "zzz"}).status_code == 400


def test_integrity_is_healthy_for_consistent_data(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    place = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Springfield",
        aliases=("Springfld",),
    )
    substrate = cleanup_session.get(SubstrateLocation, place.substrate_id)
    substrate.canonical_link_status = CANONICAL_LINK_LINKED
    cleanup_session.add(substrate)
    cleanup_session.commit()

    body = cleanup_client.get(f"{CLEANUP_BASE}/locations/integrity", headers=headers).json()

    assert body["healthy"] is True
    assert body["issues"] == []
    assert body["counts"]["canonicals"] == 1
    assert body["counts"]["linked_records"] == 1
    assert body["counts"]["aliases"] == 1


def test_integrity_reports_inconsistent_links_and_connections(
    cleanup_client, cleanup_world, cleanup_session
) -> None:
    headers = create_cleanup_key(cleanup_client)
    # Points at a canonical but is not marked linked.
    unmarked = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.stylebook_id,
        project_id=cleanup_world.project_id,
        label="Unmarked",
    )
    unmarked_record = cleanup_session.get(SubstrateLocation, unmarked.substrate_id)
    unmarked_record.canonical_link_status = CANONICAL_LINK_PENDING
    cleanup_session.add(unmarked_record)
    # Marked linked with no canonical.
    orphan = seed_substrate(
        cleanup_session,
        "locations",
        canonical_id=None,
        project_id=cleanup_world.project_id,
        name="Orphan",
        link_status=CANONICAL_LINK_LINKED,
    )
    # Linked across Stylebooks.
    foreign = seed_entity(
        cleanup_session,
        "locations",
        stylebook_id=cleanup_world.foreign_stylebook_id,
        project_id=cleanup_world.second_project_id,
        label="Foreign",
    )
    cross = cleanup_session.get(SubstrateLocation, foreign.substrate_id)
    cross.canonical_link_status = CANONICAL_LINK_LINKED
    cleanup_session.add(cross)
    # An open connection on a canonical that is not active.
    retired = cleanup_session.get(StylebookLocationCanonical, unmarked.canonical_id)
    retired.status = "inactive"
    cleanup_session.add(retired)
    cleanup_session.add(
        StylebookConnection(
            project_id=cleanup_world.project_id,
            stylebook_id=cleanup_world.stylebook_id,
            from_entity_type="location",
            from_entity_id=unmarked.canonical_id,
            to_entity_type="organization",
            to_entity_id="someone-else",
        )
    )
    cleanup_session.commit()

    body = cleanup_client.get(f"{CLEANUP_BASE}/locations/integrity", headers=headers).json()

    issues = {issue["code"]: issue for issue in body["issues"]}
    assert body["healthy"] is False
    assert issues["canonical_without_linked_state"]["sample_ids"] == [str(unmarked.substrate_id)]
    assert issues["linked_without_canonical"]["sample_ids"] == [str(orphan)]
    assert issues["cross_stylebook_reference"]["sample_ids"] == [str(foreign.substrate_id)]
    assert issues["open_connection_on_missing_or_inactive_canonical"]["count"] == 1


def test_integrity_unknown_entity_and_scope(cleanup_client, cleanup_world) -> None:
    headers = create_cleanup_key(cleanup_client, scopes=["read"])
    assert (
        cleanup_client.get(f"{CLEANUP_BASE}/locations/integrity", headers=headers).status_code
        == 403
    )
    ok_headers = create_cleanup_key(cleanup_client)
    assert (
        cleanup_client.get(f"{CLEANUP_BASE}/widgets/integrity", headers=ok_headers).status_code
        == 422
    )
