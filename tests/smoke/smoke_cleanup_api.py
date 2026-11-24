#!/usr/bin/env python3
"""Cleanup API smoke: open a run, dry-run then apply one merge, then an alias, an edit and a
dismissal on the survivor, retire, reinstate and delete a third place, and read the ledger back.

Uses only throwaway "Smoke cleanup ..." places, a throwaway service key, and removes them
afterwards (set SMOKE_KEEP_DATA=1 to keep them for inspection).
"""

from __future__ import annotations

import os
import sys
import uuid
from typing import Any

import httpx
from _helpers import (
    assert_object,
    default_stylebook_for_org,
    delete_smoke_canonical,
    ensure_health,
    http_error_detail,
    keep_smoke_data,
    log,
    login_session_context,
    session_cookie_headers,
    smoke_db_session,
)
from backfield_db import (
    StylebookActivity,
    StylebookCanonicalRedirect,
    StylebookCleanupAction,
    StylebookCleanupDismissal,
    StylebookCleanupRun,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from sqlalchemy import or_
from sqlmodel import col, delete

AGATE_API_BASE = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
STYLEBOOK_API_BASE = os.environ.get("STYLEBOOK_API_BASE", "http://localhost:8003")
CORE_API_BASE = os.environ.get("CORE_API_BASE", "http://localhost:8004")
SMOKE_EMAIL = os.environ.get("SMOKE_EMAIL", "").strip()
SMOKE_PASSWORD = os.environ.get("SMOKE_PASSWORD", "")
SMOKE_WORKSPACE_SLUG = os.environ.get("SMOKE_WORKSPACE_SLUG", "default").strip()
SMOKE_PROJECT_SLUG = os.environ.get("SMOKE_PROJECT_SLUG", "general").strip()


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _create_place(client: httpx.Client, stylebook_slug: str, project_slug: str, label: str) -> str:
    created = assert_object(
        client.post(
            f"/v1/stylebooks/{stylebook_slug}/canonical-locations",
            params={"project": project_slug},
            json={"label": label, "location_type": "city"},
        ),
        f"create {label}",
    )
    return str(created["id"])


def _apply_one(api: httpx.Client, url: str, run_id: str, item: dict[str, Any]) -> dict[str, Any]:
    """Apply one item for real and return its result, failing unless it was applied."""
    response = assert_object(
        api.post(url, json={"run_id": run_id, "dry_run": False, "items": [item]}), url
    )
    result: dict[str, Any] = response["items"][0]
    _expect(result["status"] == "applied", f"{url}: {response!r}")
    return result


def _dismissals_for_run(api: httpx.Client, base: str, run_id: str) -> list[dict[str, Any]]:
    """Page through the dismissals list (a real catalog has many) and keep this run's."""
    found: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        params = {"limit": 200, **({"cursor": cursor} if cursor else {})}
        page = assert_object(api.get(f"{base}/dismissals", params=params), "dismissals")
        found.extend(item for item in page["items"] if item["run_id"] == run_id)
        cursor = page["next_cursor"]
        if cursor is None:
            return found


def _apply_survivor_changes(
    api: httpx.Client, base: str, *, run_id: str, survivor_id: str, tag: str
) -> None:
    """An alias, a rename (which keeps the old name), and a dismissal on the merge survivor."""
    old_name = f"Smoke cleanup B {tag}"
    new_name = f"Smoke cleanup B renamed {tag}"
    _apply_one(
        api,
        f"{base}/locations/aliases",
        run_id,
        {
            "item_id": f"alias-{tag}",
            "canonical_id": survivor_id,
            "action": "add",
            "alias_text": f"Smoke cleanup nickname {tag}",
        },
    )
    edit = _apply_one(
        api,
        f"{base}/locations/edits",
        run_id,
        {"item_id": f"edit-{tag}", "canonical_id": survivor_id, "changes": {"label": new_name}},
    )
    _expect(edit["summary"]["old_name_kept_as_alias"] is True, f"rename: {edit!r}")
    _apply_one(
        api,
        f"{base}/dismissals",
        run_id,
        {
            "item_id": f"dismiss-{tag}",
            "check_id": "missing-geometry-locations",
            "canonical_id": survivor_id,
            "reason_code": "smoke",
        },
    )
    evidence = assert_object(api.get(f"{base}/locations/{survivor_id}/evidence"), "evidence")
    names = {a["alias_text"] for a in evidence["aliases"] if not a["suppressed"]}
    _expect({old_name, f"Smoke cleanup nickname {tag}"} <= names, f"aliases: {names!r}")
    mine = _dismissals_for_run(api, base, run_id)
    _expect(len(mine) == 1 and mine[0]["reason_code"] == "smoke", f"dismissals: {mine!r}")
    log("Alias, rename (old name kept) and dismissal applied and read back.")


def _apply_removals(
    api: httpx.Client, base: str, *, run_id: str, survivor_id: str, spare_id: str
) -> None:
    """Refuse to retire a place with linked records, then retire, reinstate and delete a spare."""
    refused = assert_object(
        api.post(
            f"{base}/locations/retirements",
            json={
                "run_id": run_id,
                "dry_run": False,
                "items": [{"item_id": "refuse", "canonical_id": survivor_id}],
            },
        ),
        "retire with linked records",
    )["items"][0]
    _expect(
        refused["status"] == "error" and refused["reason"] == "linked_records_present",
        f"expected a refusal: {refused!r}",
    )

    retire = f"{base}/locations/retirements"
    _apply_one(api, retire, run_id, {"item_id": "retire", "canonical_id": spare_id})
    with smoke_db_session() as session:
        place = session.get(StylebookLocationCanonical, spare_id)
        _expect(place is not None and place.status == "inactive", "retire did not stick")
    _apply_one(
        api,
        retire,
        run_id,
        {"item_id": "reinstate", "canonical_id": spare_id, "action": "reinstate"},
    )
    with smoke_db_session() as session:
        place = session.get(StylebookLocationCanonical, spare_id)
        _expect(place is not None and place.status == "active", "reinstate did not stick")

    _apply_one(
        api, f"{base}/locations/deletions", run_id, {"item_id": "delete", "canonical_id": spare_id}
    )
    with smoke_db_session() as session:
        _expect(session.get(StylebookLocationCanonical, spare_id) is None, "delete did not stick")
    resolution = assert_object(api.get(f"{base}/locations/{spare_id}/resolution"), "resolution")
    _expect(resolution["deleted"] is True, f"resolution after delete: {resolution!r}")
    log("Refusal, retire, reinstate and delete applied and read back.")


def _remove_smoke_rows(
    *,
    stylebook_id: int,
    run_id: str | None,
    source_id: str | None,
    target_id: str | None,
    spare_id: str | None,
    substrate_id: int | None,
) -> None:
    """Remove everything the scenario created, in foreign-key order."""
    place_ids = [value for value in (source_id, target_id, spare_id) if value]
    with smoke_db_session() as session:
        if place_ids:
            session.exec(
                delete(StylebookCanonicalRedirect).where(
                    StylebookCanonicalRedirect.stylebook_id == stylebook_id,
                    col(StylebookCanonicalRedirect.old_id).in_(place_ids),
                )
            )
        if run_id:
            session.exec(
                delete(StylebookCleanupDismissal).where(StylebookCleanupDismissal.run_id == run_id)
            )
            session.exec(
                delete(StylebookCleanupAction).where(StylebookCleanupAction.run_id == run_id)
            )
            session.exec(delete(StylebookCleanupRun).where(StylebookCleanupRun.id == run_id))
        if place_ids:
            session.exec(
                delete(StylebookActivity).where(
                    StylebookActivity.stylebook_id == stylebook_id,
                    StylebookActivity.source == "cleanup_api",
                    or_(
                        col(StylebookActivity.entity_id).in_(place_ids),
                        col(StylebookActivity.related_entity_id).in_(place_ids),
                    ),
                )
            )
            session.exec(
                delete(StylebookActivity).where(
                    StylebookActivity.stylebook_id == stylebook_id,
                    StylebookActivity.entity_type == "location",
                    col(StylebookActivity.entity_id).in_(place_ids),
                )
            )
        linked: set[int] = {substrate_id} if substrate_id is not None else set()
        for canonical_id in place_ids:
            if session.get(StylebookLocationCanonical, canonical_id) is not None:
                delete_smoke_canonical(
                    session, canonical_id=canonical_id, allowed_linked_location_ids=linked
                )
        if substrate_id is not None:
            session.exec(delete(SubstrateLocation).where(SubstrateLocation.id == substrate_id))
        session.commit()


def main() -> int:
    if not SMOKE_EMAIL or not SMOKE_PASSWORD:
        raise RuntimeError("smoke-cleanup-api requires SMOKE_EMAIL and SMOKE_PASSWORD")

    ctx = login_session_context(
        core_base=CORE_API_BASE,
        email=SMOKE_EMAIL,
        password=SMOKE_PASSWORD,
        workspace_slug=SMOKE_WORKSPACE_SLUG,
        project_slug=SMOKE_PROJECT_SLUG,
    )
    session_headers = session_cookie_headers(ctx.session_token)
    ensure_health(
        agate_base=AGATE_API_BASE,
        stylebook_base=STYLEBOOK_API_BASE,
        core_base=CORE_API_BASE,
        agate_headers=session_headers,
        stylebook_headers=session_headers,
    )
    stylebook = default_stylebook_for_org(
        stylebook_base=STYLEBOOK_API_BASE,
        session_token=ctx.session_token,
        organization_id=ctx.organization_id,
    )
    stylebook_slug = str(stylebook["slug"])
    stylebook_id = int(stylebook["id"])
    base = f"/public/v1/projects/{ctx.project_slug}/stylebooks/{stylebook_slug}/cleanup"
    tag = uuid.uuid4().hex[:8]

    credential_id: int | None = None
    run_id: str | None = None
    source_id: str | None = None
    target_id: str | None = None
    spare_id: str | None = None
    substrate_id: int | None = None
    try:
        with (
            httpx.Client(base_url=STYLEBOOK_API_BASE, timeout=15.0, headers=session_headers) as sb,
            httpx.Client(base_url=CORE_API_BASE, timeout=30.0, headers=session_headers) as core,
        ):
            source_id = _create_place(
                sb, stylebook_slug, ctx.project_slug, f"Smoke cleanup A {tag}"
            )
            target_id = _create_place(
                sb, stylebook_slug, ctx.project_slug, f"Smoke cleanup B {tag}"
            )
            spare_id = _create_place(sb, stylebook_slug, ctx.project_slug, f"Smoke cleanup C {tag}")
            with smoke_db_session() as session:
                substrate = SubstrateLocation(
                    project_id=ctx.project_id,
                    name=f"Smoke cleanup A {tag}",
                    normalized_name=f"smoke cleanup a {tag}",
                    stylebook_location_canonical_id=source_id,
                    canonical_link_status="linked",
                )
                session.add(substrate)
                session.commit()
                substrate_id = int(substrate.id)  # type: ignore[arg-type]

            key = assert_object(
                core.post(
                    f"/v1/projects/{ctx.project_id}/api-keys",
                    json={
                        "credential_type": "service",
                        "scopes": ["cleanup:apply"],
                        "label": f"smoke cleanup {tag}",
                    },
                ),
                "create service key",
            )
            credential_id = int(key["id"])
            bearer = {"Authorization": f"Bearer {key['raw_key']}"}

        with httpx.Client(base_url=CORE_API_BASE, timeout=60.0, headers=bearer) as api:
            capabilities = assert_object(api.get(f"{base}/capabilities"), "capabilities")
            _expect(capabilities.get("contract_version") == "preview-1", f"{capabilities!r}")
            operations = capabilities.get("operations", [])
            for operation in (
                "merges",
                "edits",
                "aliases",
                "dismissals",
                "retirements",
                "deletions",
            ):
                _expect(operation in operations, f"{operation} missing: {capabilities!r}")
            log("Capabilities advertise every cleanup operation.")

            run = assert_object(
                api.post(f"{base}/runs", json={"label": f"smoke {tag}", "client_run_ref": tag}),
                "open run",
            )
            run_id = str(run["id"])
            _expect(run["status"] == "open", f"{run!r}")

            item: dict[str, Any] = {
                "item_id": f"smoke-{tag}",
                "source_id": source_id,
                "target_id": target_id,
                "provenance": {"reason": "smoke"},
            }
            preview = assert_object(
                api.post(f"{base}/locations/merges", json={"run_id": run_id, "items": [item]}),
                "dry-run merge",
            )
            _expect(preview["dry_run"] is True, f"{preview!r}")
            _expect(preview["counts"]["would_apply"] == 1, f"dry run: {preview!r}")
            still_there = api.get(
                f"{base}/locations/{source_id}/resolution",
            ).json()
            _expect(still_there["merged"] is False, f"dry run changed data: {still_there!r}")
            with smoke_db_session() as session:
                _expect(
                    session.get(StylebookLocationCanonical, source_id) is not None,
                    "dry run removed the source canonical",
                )
            log("Dry run reported would_apply and changed nothing.")

            applied = assert_object(
                api.post(
                    f"{base}/locations/merges",
                    json={"run_id": run_id, "dry_run": False, "items": [item]},
                ),
                "applied merge",
            )
            result = applied["items"][0]
            _expect(result["status"] == "applied", f"apply: {applied!r}")
            action_id = str(result["action_id"])
            with smoke_db_session() as session:
                _expect(
                    session.get(StylebookLocationCanonical, source_id) is None,
                    "source canonical survived the merge",
                )
                moved = session.get(SubstrateLocation, substrate_id)
                _expect(
                    moved is not None and moved.stylebook_location_canonical_id == target_id,
                    "linked record did not move to the survivor",
                )
            log(f"Merge applied (action {action_id}); linked record moved to the survivor.")

            resolution = assert_object(
                api.get(f"{base}/locations/{source_id}/resolution"), "resolution"
            )
            _expect(
                resolution["merged"] is True and resolution["resolved_id"] == target_id,
                f"resolution: {resolution!r}",
            )

            actions = assert_object(api.get(f"{base}/runs/{run_id}/actions"), "run actions")
            _expect([a["id"] for a in actions["items"]] == [action_id], f"{actions!r}")
            action = assert_object(api.get(f"{base}/actions/{action_id}"), "action")
            _expect(action["before_state"] is not None, "ledger row has no before-state")
            _expect(action["client_item_id"] == item["item_id"], f"{action!r}")

            repeat = assert_object(
                api.post(
                    f"{base}/locations/merges",
                    json={"run_id": run_id, "dry_run": False, "items": [item]},
                ),
                "repeat merge",
            )
            repeated = repeat["items"][0]
            _expect(
                repeated["status"] == "noop" and repeated["reason"] == "already_merged",
                f"repeat: {repeat!r}",
            )
            log("Ledger, resolution, and repeat-merge noop check out.")

            _apply_survivor_changes(api, base, run_id=run_id, survivor_id=target_id, tag=tag)

            _apply_removals(api, base, run_id=run_id, survivor_id=target_id, spare_id=spare_id)

            closed = assert_object(
                api.post(f"{base}/runs/{run_id}/close", json={"status": "closed"}), "close run"
            )
            _expect(closed["status"] == "closed", f"{closed!r}")
            _expect(closed["action_counts"].get("merge") == 1, f"{closed!r}")

        log("Smoke cleanup API passed.")
        log(f"Stylebook: {stylebook_slug!r}  Run: {run_id}")
        return 0
    finally:
        if not keep_smoke_data():
            _remove_smoke_rows(
                stylebook_id=stylebook_id,
                run_id=run_id,
                source_id=source_id,
                target_id=target_id,
                spare_id=spare_id,
                substrate_id=substrate_id,
            )
            if credential_id is not None:
                with httpx.Client(
                    base_url=CORE_API_BASE, timeout=15.0, headers=session_headers
                ) as core:
                    core.delete(f"/v1/projects/{ctx.project_id}/api-keys/{credential_id}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPError as exc:
        print(f"HTTP smoke failure: {http_error_detail(exc)}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Smoke failure: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
