"""Persisted cleanup check runs: scope hashing, item building, and cached reads."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from backfield_db import (
    StylebookCleanupCheckResult,
    StylebookCleanupCheckRun,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from sqlmodel import Session, col, delete, select

from backfield_entities.quality.checks import cleanup_check_by_id
from backfield_entities.quality.dismissals import (
    all_pairs_for_members,
    canonical_dismissal_key,
    load_dismissed_keys,
    pair_key_for_ids,
)
from backfield_entities.quality.finders._duplicate_labels import load_canonical_labels
from backfield_entities.quality.finders.duplicate_locations import (
    cluster_display_label as location_cluster_display_label,
)
from backfield_entities.quality.finders.duplicate_locations import (
    duplicate_location_cluster_ids,
)
from backfield_entities.quality.finders.duplicate_organizations import (
    duplicate_organization_cluster_ids,
    organization_cluster_display_label,
)
from backfield_entities.quality.finders.duplicate_people import (
    duplicate_person_cluster_ids,
    person_cluster_display_label,
)
from backfield_entities.quality.finders.location_geography_issues import (
    list_location_geography_issues,
)
from backfield_entities.quality.finders.location_name_mismatch import (
    list_location_name_mismatches,
)
from backfield_entities.quality.finders.organization_name_mismatch import (
    list_organization_name_mismatches,
)
from backfield_entities.quality.finders.person_name_mismatch import (
    list_person_name_mismatches,
)
from backfield_entities.quality.types import (
    CleanupLocationGeographyIssueRow,
    CleanupNameMismatchIssueRow,
)

CleanupItemKind = Literal["cluster", "list"]
_ACTIVE_RUN_STATUSES: frozenset[str] = frozenset({"queued", "running"})
_LIST_BATCH_SIZE = 500

_ALGORITHM_VERSIONS: dict[str, str] = {
    "duplicate-locations": "duplicate-locations:v1",
    "duplicate-people": "duplicate-people:v1",
    "duplicate-organizations": "duplicate-organizations:v1",
    "missing-geometry-locations": "missing-geometry-locations:v1",
    "mismatched-locations": "mismatched-locations:v1",
    "mismatched-people": "mismatched-people:v1",
    "mismatched-organizations": "mismatched-organizations:v1",
}


@dataclass(frozen=True)
class CleanupRunScope:
    stylebook_id: int
    organization_id: int
    check_id: str
    full_threshold: float
    head_threshold: float
    project_ids: tuple[int, ...] | None = None
    project_slug: str | None = None


@dataclass(frozen=True)
class CleanupCheckItem:
    item_kind: CleanupItemKind
    item_key: str
    label: str | None
    canonical_ids: list[str]
    pair_keys: list[str]
    payload: dict[str, Any] | None
    searchable_text: str


def cleanup_algorithm_version(check_id: str) -> str:
    version = _ALGORITHM_VERSIONS.get(check_id)
    if version is None:
        raise ValueError(f"Unknown cleanup check id: {check_id}")
    return version


def cleanup_scope_hash(scope: CleanupRunScope) -> str:
    payload = {
        "stylebook_id": scope.stylebook_id,
        "organization_id": scope.organization_id,
        "check_id": scope.check_id,
        "full_threshold": scope.full_threshold,
        "head_threshold": scope.head_threshold,
        "project_ids": list(scope.project_ids) if scope.project_ids is not None else None,
        "project_slug": scope.project_slug,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def scope_to_json(scope: CleanupRunScope) -> dict[str, Any]:
    return {
        "stylebook_id": scope.stylebook_id,
        "organization_id": scope.organization_id,
        "check_id": scope.check_id,
        "full_threshold": scope.full_threshold,
        "head_threshold": scope.head_threshold,
        "project_ids": list(scope.project_ids) if scope.project_ids is not None else None,
        "project_slug": scope.project_slug,
    }


def _searchable_cluster_text(label: str, member_labels: list[str]) -> str:
    parts = [label, *member_labels]
    return " ".join(part.strip() for part in parts if part and part.strip()).lower()


def _searchable_list_text(label: str, extra: list[str]) -> str:
    parts = [label, *extra]
    return " ".join(part.strip() for part in parts if part and part.strip()).lower()


def _cluster_items_from_ids(
    *,
    clusters: list[list[str]],
    labels_by_id: dict[str, str],
    display_label_fn,
) -> list[CleanupCheckItem]:
    items: list[CleanupCheckItem] = []
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        member_ids = sorted(cluster)
        member_labels = [labels_by_id.get(member_id, member_id) for member_id in member_ids]
        label = display_label_fn(member_labels)
        pair_keys = [
            pair_key_for_ids(left_id, right_id)
            for left_id, right_id in all_pairs_for_members(member_ids)
        ]
        cluster_key = member_ids[0]
        items.append(
            CleanupCheckItem(
                item_kind="cluster",
                item_key=f"{cluster_key}:{len(member_ids)}",
                label=label,
                canonical_ids=member_ids,
                pair_keys=pair_keys,
                payload={},
                searchable_text=_searchable_cluster_text(label, member_labels),
            )
        )
    return items


def _list_all_rows(
    fetch_page,
) -> list[Any]:
    offset = 0
    rows: list[Any] = []
    while True:
        page, total = fetch_page(limit=_LIST_BATCH_SIZE, offset=offset)
        rows.extend(page)
        if offset + len(page) >= total:
            break
        offset += _LIST_BATCH_SIZE
    return rows


def _geography_list_items(
    session: Session,
    *,
    scope: CleanupRunScope,
) -> list[CleanupCheckItem]:
    project_ids = list(scope.project_ids) if scope.project_ids is not None else None

    def fetch_page(
        *, limit: int, offset: int
    ) -> tuple[list[CleanupLocationGeographyIssueRow], int]:
        return list_location_geography_issues(
            session,
            stylebook_id=scope.stylebook_id,
            organization_id=scope.organization_id,
            project_ids=project_ids,
            limit=limit,
            offset=offset,
        )

    rows = _list_all_rows(fetch_page)
    items: list[CleanupCheckItem] = []
    for row in rows:
        canonical_id = str(row.id)
        items.append(
            CleanupCheckItem(
                item_kind="list",
                item_key=canonical_id,
                label=row.label,
                canonical_ids=[canonical_id],
                pair_keys=[canonical_dismissal_key(canonical_id)],
                payload={
                    "geography_issue": row.issue,
                    "distant_linked_count": int(row.distant_linked_count),
                },
                searchable_text=_searchable_list_text(row.label, []),
            )
        )
    return items


def _mismatch_list_items(
    session: Session,
    *,
    scope: CleanupRunScope,
    fetch_page,
) -> list[CleanupCheckItem]:
    rows = _list_all_rows(fetch_page)
    items: list[CleanupCheckItem] = []
    for row in rows:
        canonical_id = str(row.id)
        examples = list(row.mismatched_examples)
        items.append(
            CleanupCheckItem(
                item_kind="list",
                item_key=canonical_id,
                label=row.label,
                canonical_ids=[canonical_id],
                pair_keys=[canonical_dismissal_key(canonical_id)],
                payload={
                    "mismatched_linked_count": int(row.mismatched_linked_count),
                    "mismatched_examples": examples,
                },
                searchable_text=_searchable_list_text(row.label, examples),
            )
        )
    return items


def build_cleanup_check_items(
    session: Session,
    *,
    scope: CleanupRunScope,
) -> list[CleanupCheckItem]:
    check_id = scope.check_id
    stylebook_id = scope.stylebook_id

    if check_id == "duplicate-locations":
        clusters = duplicate_location_cluster_ids(
            session,
            stylebook_id=stylebook_id,
            full_threshold=scope.full_threshold,
            head_threshold=scope.head_threshold,
        )
        all_ids = sorted({member_id for cluster in clusters for member_id in cluster})
        labels_by_id = load_canonical_labels(session, StylebookLocationCanonical, all_ids)
        return _cluster_items_from_ids(
            clusters=clusters,
            labels_by_id=labels_by_id,
            display_label_fn=location_cluster_display_label,
        )

    if check_id == "duplicate-people":
        clusters = duplicate_person_cluster_ids(
            session,
            stylebook_id=stylebook_id,
            full_threshold=scope.full_threshold,
        )
        all_ids = sorted({member_id for cluster in clusters for member_id in cluster})
        labels_by_id = load_canonical_labels(session, StylebookPersonCanonical, all_ids)
        return _cluster_items_from_ids(
            clusters=clusters,
            labels_by_id=labels_by_id,
            display_label_fn=person_cluster_display_label,
        )

    if check_id == "duplicate-organizations":
        clusters = duplicate_organization_cluster_ids(
            session,
            stylebook_id=stylebook_id,
            full_threshold=scope.full_threshold,
        )
        all_ids = sorted({member_id for cluster in clusters for member_id in cluster})
        labels_by_id = load_canonical_labels(session, StylebookOrganizationCanonical, all_ids)
        return _cluster_items_from_ids(
            clusters=clusters,
            labels_by_id=labels_by_id,
            display_label_fn=organization_cluster_display_label,
        )

    if check_id == "missing-geometry-locations":
        return _geography_list_items(session, scope=scope)

    if check_id == "mismatched-people":

        def fetch_page(*, limit: int, offset: int) -> tuple[list[CleanupNameMismatchIssueRow], int]:
            return list_person_name_mismatches(
                session,
                stylebook_id=scope.stylebook_id,
                organization_id=scope.organization_id,
                limit=limit,
                offset=offset,
            )

        return _mismatch_list_items(session, scope=scope, fetch_page=fetch_page)

    if check_id == "mismatched-organizations":

        def fetch_page(*, limit: int, offset: int) -> tuple[list[CleanupNameMismatchIssueRow], int]:
            return list_organization_name_mismatches(
                session,
                stylebook_id=scope.stylebook_id,
                organization_id=scope.organization_id,
                limit=limit,
                offset=offset,
            )

        return _mismatch_list_items(session, scope=scope, fetch_page=fetch_page)

    if check_id == "mismatched-locations":

        def fetch_page(*, limit: int, offset: int) -> tuple[list[CleanupNameMismatchIssueRow], int]:
            return list_location_name_mismatches(
                session,
                stylebook_id=scope.stylebook_id,
                organization_id=scope.organization_id,
                limit=limit,
                offset=offset,
            )

        return _mismatch_list_items(session, scope=scope, fetch_page=fetch_page)

    raise ValueError(f"Unknown cleanup check id: {check_id}")


def persist_cleanup_check_results(
    session: Session,
    *,
    run: StylebookCleanupCheckRun,
    items: list[CleanupCheckItem],
) -> int:
    session.exec(
        delete(StylebookCleanupCheckResult).where(
            StylebookCleanupCheckResult.run_id == run.id
        )
    )
    for ordinal, item in enumerate(items):
        session.add(
            StylebookCleanupCheckResult(
                run_id=str(run.id),
                stylebook_id=int(run.stylebook_id),
                check_id=str(run.check_id),
                ordinal=ordinal,
                item_kind=item.item_kind,
                item_key=item.item_key,
                label=item.label,
                canonical_ids_json=list(item.canonical_ids),
                pair_keys_json=list(item.pair_keys),
                payload_json=item.payload,
                searchable_text=item.searchable_text,
            )
        )
    run.candidate_count = len(items)
    run.updated_at = datetime.now(UTC)
    session.add(run)
    return len(items)


def get_latest_cleanup_check_run(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str,
    scope_hash: str,
) -> StylebookCleanupCheckRun | None:
    return session.exec(
        select(StylebookCleanupCheckRun)
        .where(
            StylebookCleanupCheckRun.stylebook_id == stylebook_id,
            StylebookCleanupCheckRun.check_id == check_id,
            StylebookCleanupCheckRun.scope_hash == scope_hash,
        )
        .order_by(col(StylebookCleanupCheckRun.created_at).desc())
    ).first()


def get_active_cleanup_check_run(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str,
    scope_hash: str,
) -> StylebookCleanupCheckRun | None:
    return session.exec(
        select(StylebookCleanupCheckRun)
        .where(
            StylebookCleanupCheckRun.stylebook_id == stylebook_id,
            StylebookCleanupCheckRun.check_id == check_id,
            StylebookCleanupCheckRun.scope_hash == scope_hash,
            col(StylebookCleanupCheckRun.status).in_(_ACTIVE_RUN_STATUSES),
        )
        .order_by(col(StylebookCleanupCheckRun.created_at).desc())
    ).first()


def get_latest_succeeded_cleanup_check_run(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str,
    scope_hash: str,
) -> StylebookCleanupCheckRun | None:
    return session.exec(
        select(StylebookCleanupCheckRun)
        .where(
            StylebookCleanupCheckRun.stylebook_id == stylebook_id,
            StylebookCleanupCheckRun.check_id == check_id,
            StylebookCleanupCheckRun.scope_hash == scope_hash,
            StylebookCleanupCheckRun.status == "succeeded",
        )
        .order_by(col(StylebookCleanupCheckRun.completed_at).desc())
    ).first()


def load_existing_canonical_ids_for_check(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str,
    candidate_ids: set[str],
) -> set[str]:
    """Return which cached canonical ids still exist for a cleanup check."""
    if not candidate_ids:
        return set()
    if check_id in (
        "duplicate-locations",
        "missing-geometry-locations",
        "mismatched-locations",
    ):
        model = StylebookLocationCanonical
    elif check_id in ("duplicate-people", "mismatched-people"):
        model = StylebookPersonCanonical
    elif check_id in ("duplicate-organizations", "mismatched-organizations"):
        model = StylebookOrganizationCanonical
    else:
        return set(candidate_ids)
    rows = session.exec(
        select(model.id).where(
            model.stylebook_id == stylebook_id,
            col(model.id).in_(candidate_ids),
        )
    ).all()
    return {str(row) for row in rows}


def _candidate_canonical_ids_from_results(
    results: list[StylebookCleanupCheckResult],
) -> set[str]:
    candidate_ids: set[str] = set()
    for result in results:
        candidate_ids.update(str(cid) for cid in (result.canonical_ids_json or []))
    return candidate_ids


def _existing_canonical_ids_for_results(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str,
    results: list[StylebookCleanupCheckResult],
) -> set[str]:
    return load_existing_canonical_ids_for_check(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
        candidate_ids=_candidate_canonical_ids_from_results(results),
    )


def is_result_dismissed(
    result: StylebookCleanupCheckResult,
    *,
    dismissed_keys: set[str],
) -> bool:
    if not dismissed_keys:
        return False
    if result.item_kind == "list":
        pair_keys = result.pair_keys_json or []
        return bool(pair_keys) and pair_keys[0] in dismissed_keys
    pair_keys = result.pair_keys_json or []
    if not pair_keys:
        return False
    return all(pair_key in dismissed_keys for pair_key in pair_keys)


def filter_visible_cached_results(
    results: list[StylebookCleanupCheckResult],
    *,
    dismissed_keys: set[str],
    existing_canonical_ids: set[str],
) -> list[StylebookCleanupCheckResult]:
    visible: list[StylebookCleanupCheckResult] = []
    for result in results:
        if is_result_dismissed(result, dismissed_keys=dismissed_keys):
            continue
        canonical_ids = [str(cid) for cid in (result.canonical_ids_json or [])]
        if result.item_kind == "cluster":
            member_ids = [cid for cid in canonical_ids if cid in existing_canonical_ids]
            if len(member_ids) < 2:
                continue
        elif not canonical_ids or canonical_ids[0] not in existing_canonical_ids:
            continue
        visible.append(result)
    return visible


def query_cached_check_results(
    session: Session,
    *,
    run_id: str,
    stylebook_id: int,
    check_id: str,
    limit: int,
    offset: int,
    query: str | None = None,
) -> tuple[list[StylebookCleanupCheckResult], int]:
    dismissed_keys = load_dismissed_keys(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
    )
    stmt = (
        select(StylebookCleanupCheckResult)
        .where(StylebookCleanupCheckResult.run_id == run_id)
        .order_by(StylebookCleanupCheckResult.ordinal)
    )
    if query and query.strip():
        needle = query.strip().lower()
        stmt = stmt.where(col(StylebookCleanupCheckResult.searchable_text).contains(needle))
    rows = list(session.exec(stmt).all())
    existing_canonical_ids = _existing_canonical_ids_for_results(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
        results=rows,
    )
    visible = filter_visible_cached_results(
        rows,
        dismissed_keys=dismissed_keys,
        existing_canonical_ids=existing_canonical_ids,
    )
    total = len(visible)
    page = visible[offset : offset + limit]
    return page, total


def count_visible_cached_results(
    session: Session,
    *,
    run_id: str,
    stylebook_id: int,
    check_id: str,
) -> int:
    dismissed_keys = load_dismissed_keys(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
    )
    rows = list(
        session.exec(
            select(StylebookCleanupCheckResult)
            .where(StylebookCleanupCheckResult.run_id == run_id)
            .order_by(StylebookCleanupCheckResult.ordinal)
        ).all()
    )
    existing_canonical_ids = _existing_canonical_ids_for_results(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
        results=rows,
    )
    visible = filter_visible_cached_results(
        rows,
        dismissed_keys=dismissed_keys,
        existing_canonical_ids=existing_canonical_ids,
    )
    return len(visible)


def validate_cleanup_check_id(check_id: str) -> str:
    normalized = check_id.strip()
    if cleanup_check_by_id(normalized) is None:
        raise ValueError(f"Unknown cleanup check: {normalized}")
    return normalized
