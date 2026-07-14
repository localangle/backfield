"""Full stylebook ZIP export/import (manifest + sharded JSONL).

See docs/operations/runtime-configuration.md for S3 staging settings.
See docs/api/stylebook.md for bundle import, transfer, and cleanup behavior.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backfield_db import (
    BackfieldProject,
    Stylebook,
    StylebookConnection,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    StylebookLocationMeta,
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    StylebookOrganizationMeta,
    StylebookPersonAlias,
    StylebookPersonCanonical,
    StylebookPersonMeta,
)
from sqlmodel import Session, col, select

from backfield_entities.canonical.slug import allocate_unique_canonical_slug
from backfield_entities.catalog.stylebook_library import (
    StylebookLibraryError,
    create_stylebook_for_import,
)
from backfield_entities.entities.location.persist import seed_aliases_for_canonical_label
from backfield_entities.entities.organization.persist import (
    allocate_unique_organization_canonical_slug,
    organization_canonical_to_export_dict,
)
from backfield_entities.entities.organization.persist import (
    seed_aliases_for_canonical_label as seed_organization_aliases_for_canonical_label,
)
from backfield_entities.entities.person.persist import (
    allocate_unique_person_canonical_slug,
)
from backfield_entities.entities.person.persist import (
    seed_aliases_for_canonical_label as seed_person_aliases_for_canonical_label,
)
from backfield_entities.entities.person.types import derive_person_sort_key

# v2: location canonical rows only (legacy path ``canonicals/part-*.jsonl``, kind ``canonical``).
# v3: per-entity shards under ``canonicals/{entity}/`` with kinds ``canonical_location``, …
# v4: adds aliases, project-scoped meta, and connections (see docs/api/stylebook.md).
BUNDLE_SCHEMA_VERSION = 4
ALLOWED_MANIFEST_SCHEMA_VERSIONS = frozenset({1, 2, 3, 4})
BUNDLE_KIND_LEGACY_LOCATION = "canonical"
BUNDLE_KIND_LOCATION = "canonical_location"
BUNDLE_KIND_PERSON = "canonical_person"
BUNDLE_KIND_ORGANIZATION = "canonical_organization"
BUNDLE_KIND_ALIAS_LOCATION = "alias_location"
BUNDLE_KIND_ALIAS_PERSON = "alias_person"
BUNDLE_KIND_ALIAS_ORGANIZATION = "alias_organization"
BUNDLE_KIND_META_LOCATION = "meta_location"
BUNDLE_KIND_META_PERSON = "meta_person"
BUNDLE_KIND_META_ORGANIZATION = "meta_organization"
BUNDLE_KIND_CONNECTION = "connection"
CANONICAL_KINDS = frozenset(
    {
        BUNDLE_KIND_LEGACY_LOCATION,
        BUNDLE_KIND_LOCATION,
        BUNDLE_KIND_PERSON,
        BUNDLE_KIND_ORGANIZATION,
    }
)
ALIAS_KINDS = frozenset(
    {
        BUNDLE_KIND_ALIAS_LOCATION,
        BUNDLE_KIND_ALIAS_PERSON,
        BUNDLE_KIND_ALIAS_ORGANIZATION,
    }
)
META_KINDS = frozenset(
    {
        BUNDLE_KIND_META_LOCATION,
        BUNDLE_KIND_META_PERSON,
        BUNDLE_KIND_META_ORGANIZATION,
    }
)
ROWS_PER_SHARD = 2000
DEFAULT_MAX_ZIP_BYTES = 512 * 1024 * 1024  # 512 MiB guardrail
BUNDLE_IMPORT_PROVENANCE = "stylebook_bundle_import"

ProgressFn = Callable[[dict[str, Any]], None]


def _iso_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def location_canonical_to_export_dict(c: StylebookLocationCanonical) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "label": c.label,
        "slug": c.slug,
        "location_type": c.location_type,
        "formatted_address": c.formatted_address,
        "primary_substrate_location_id": None,
        "status": c.status,
        "geometry_type": c.geometry_type,
        "geometry_json": c.geometry_json,
        "country_code": c.country_code,
        "subdivision_code": c.subdivision_code,
        "city_name": c.city_name,
        "district_kind": c.district_kind,
        "district_number": c.district_number,
        "district_key": c.district_key,
        "created_at": _iso_utc(c.created_at),
        "updated_at": _iso_utc(c.updated_at),
    }


def person_canonical_to_export_dict(c: StylebookPersonCanonical) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "label": c.label,
        "slug": c.slug,
        "title": c.title,
        "affiliation": c.affiliation,
        "public_figure": c.public_figure,
        "person_type": c.person_type,
        "sort_key": c.sort_key,
        "primary_substrate_person_id": None,
        "status": c.status,
        "created_at": _iso_utc(c.created_at),
        "updated_at": _iso_utc(c.updated_at),
    }


def _write_jsonl_shards(
    work: Path,
    rel_prefix: str,
    rows: Iterator[dict[str, Any]],
    *,
    kind: str,
    project_slug: str | None,
    rows_per_shard: int,
) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    part = 1
    batch: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal part, batch
        if not batch:
            return
        rel = f"{rel_prefix}/part-{part:05d}.jsonl"
        full = work / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(json.dumps(r, default=str) + "\n" for r in batch)
        full.write_text(body, encoding="utf-8")
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        entry: dict[str, Any] = {
            "path": rel.replace("\\", "/"),
            "kind": kind,
            "rows": len(batch),
            "sha256": digest,
        }
        if project_slug is not None:
            entry["project_slug"] = project_slug
        files.append(entry)
        part += 1
        batch = []

    for row in rows:
        batch.append(row)
        if len(batch) >= rows_per_shard:
            flush()
    flush()
    return files


def _stylebook_canonical_id_sets(
    session: Session,
    stylebook_id: int,
) -> tuple[set[str], set[str], set[str]]:
    location_ids = {
        str(row)
        for row in session.exec(
            select(StylebookLocationCanonical.id).where(
                StylebookLocationCanonical.stylebook_id == stylebook_id,
            )
        ).all()
        if row is not None
    }
    person_ids = {
        str(row)
        for row in session.exec(
            select(StylebookPersonCanonical.id).where(
                StylebookPersonCanonical.stylebook_id == stylebook_id,
            )
        ).all()
    }
    organization_ids = {
        str(row)
        for row in session.exec(
            select(StylebookOrganizationCanonical.id).where(
                StylebookOrganizationCanonical.stylebook_id == stylebook_id,
            )
        ).all()
    }
    return location_ids, person_ids, organization_ids


def _entity_in_stylebook(
    entity_type: str,
    entity_id: str,
    *,
    location_ids: set[str],
    person_ids: set[str],
    organization_ids: set[str],
) -> bool:
    if entity_type == "location":
        return entity_id in location_ids
    if entity_type == "person":
        return entity_id in person_ids
    if entity_type == "organization":
        return entity_id in organization_ids
    return False


def _connection_belongs_to_stylebook(
    conn: StylebookConnection,
    *,
    location_ids: set[str],
    person_ids: set[str],
    organization_ids: set[str],
) -> bool:
    from_ok = _entity_in_stylebook(
        str(conn.from_entity_type),
        str(conn.from_entity_id),
        location_ids=location_ids,
        person_ids=person_ids,
        organization_ids=organization_ids,
    )
    to_ok = _entity_in_stylebook(
        str(conn.to_entity_type),
        str(conn.to_entity_id),
        location_ids=location_ids,
        person_ids=person_ids,
        organization_ids=organization_ids,
    )
    return from_ok and to_ok


def _iter_location_canonicals(
    session: Session, stylebook_id: int
) -> Iterator[StylebookLocationCanonical]:
    offset = 0
    page = 500
    while True:
        batch = session.exec(
            select(StylebookLocationCanonical)
            .where(StylebookLocationCanonical.stylebook_id == stylebook_id)
            .order_by(col(StylebookLocationCanonical.id))
            .offset(offset)
            .limit(page)
        ).all()
        if not batch:
            break
        yield from batch
        offset += page


def _iter_organization_canonicals(
    session: Session, stylebook_id: int
) -> Iterator[StylebookOrganizationCanonical]:
    offset = 0
    page = 500
    while True:
        batch = session.exec(
            select(StylebookOrganizationCanonical)
            .where(StylebookOrganizationCanonical.stylebook_id == stylebook_id)
            .order_by(col(StylebookOrganizationCanonical.id))
            .offset(offset)
            .limit(page)
        ).all()
        if not batch:
            break
        yield from batch
        offset += page


def _iter_person_canonicals(
    session: Session, stylebook_id: int
) -> Iterator[StylebookPersonCanonical]:
    offset = 0
    page = 500
    while True:
        batch = session.exec(
            select(StylebookPersonCanonical)
            .where(StylebookPersonCanonical.stylebook_id == stylebook_id)
            .order_by(col(StylebookPersonCanonical.id))
            .offset(offset)
            .limit(page)
        ).all()
        if not batch:
            break
        yield from batch
        offset += page


def _iter_location_aliases(
    session: Session, stylebook_id: int
) -> Iterator[dict[str, Any]]:
    offset = 0
    page = 500
    while True:
        batch = session.exec(
            select(StylebookLocationAlias, StylebookLocationCanonical.id)
            .join(
                StylebookLocationCanonical,
                StylebookLocationAlias.location_canonical_id == StylebookLocationCanonical.id,
            )
            .where(StylebookLocationCanonical.stylebook_id == stylebook_id)
            .order_by(col(StylebookLocationAlias.id))
            .offset(offset)
            .limit(page)
        ).all()
        if not batch:
            break
        for alias, canonical_id in batch:
            yield {
                "canonical_id": str(canonical_id),
                "alias_text": alias.alias_text,
                "normalized_alias": alias.normalized_alias,
                "provenance": alias.provenance,
                "suppressed": bool(alias.suppressed),
            }
        offset += page


def _iter_person_aliases(session: Session, stylebook_id: int) -> Iterator[dict[str, Any]]:
    offset = 0
    page = 500
    while True:
        batch = session.exec(
            select(StylebookPersonAlias, StylebookPersonCanonical.id)
            .join(
                StylebookPersonCanonical,
                StylebookPersonAlias.person_canonical_id == StylebookPersonCanonical.id,
            )
            .where(StylebookPersonCanonical.stylebook_id == stylebook_id)
            .order_by(col(StylebookPersonAlias.id))
            .offset(offset)
            .limit(page)
        ).all()
        if not batch:
            break
        for alias, canonical_id in batch:
            yield {
                "canonical_id": str(canonical_id),
                "alias_text": alias.alias_text,
                "normalized_alias": alias.normalized_alias,
                "provenance": alias.provenance,
                "suppressed": bool(alias.suppressed),
            }
        offset += page


def _iter_organization_aliases(
    session: Session, stylebook_id: int
) -> Iterator[dict[str, Any]]:
    offset = 0
    page = 500
    while True:
        batch = session.exec(
            select(StylebookOrganizationAlias, StylebookOrganizationCanonical.id)
            .join(
                StylebookOrganizationCanonical,
                StylebookOrganizationAlias.organization_canonical_id
                == StylebookOrganizationCanonical.id,
            )
            .where(StylebookOrganizationCanonical.stylebook_id == stylebook_id)
            .order_by(col(StylebookOrganizationAlias.id))
            .offset(offset)
            .limit(page)
        ).all()
        if not batch:
            break
        for alias, canonical_id in batch:
            yield {
                "canonical_id": str(canonical_id),
                "alias_text": alias.alias_text,
                "normalized_alias": alias.normalized_alias,
                "provenance": alias.provenance,
                "suppressed": bool(alias.suppressed),
            }
        offset += page


def _iter_location_meta(session: Session, stylebook_id: int) -> Iterator[dict[str, Any]]:
    offset = 0
    page = 500
    while True:
        batch = session.exec(
            select(StylebookLocationMeta, BackfieldProject.slug)
            .join(
                StylebookLocationCanonical,
                StylebookLocationMeta.stylebook_location_canonical_id
                == StylebookLocationCanonical.id,
            )
            .join(BackfieldProject, StylebookLocationMeta.project_id == BackfieldProject.id)
            .where(StylebookLocationCanonical.stylebook_id == stylebook_id)
            .order_by(col(StylebookLocationMeta.id))
            .offset(offset)
            .limit(page)
        ).all()
        if not batch:
            break
        for meta, project_slug in batch:
            yield {
                "canonical_id": str(meta.stylebook_location_canonical_id),
                "project_slug": str(project_slug),
                "meta_type": meta.meta_type,
                "data_json": meta.data_json,
                "added": bool(meta.added),
                "edited": bool(meta.edited),
                "deleted": bool(meta.deleted),
            }
        offset += page


def _iter_person_meta(session: Session, stylebook_id: int) -> Iterator[dict[str, Any]]:
    offset = 0
    page = 500
    while True:
        batch = session.exec(
            select(StylebookPersonMeta, BackfieldProject.slug)
            .join(
                StylebookPersonCanonical,
                StylebookPersonMeta.stylebook_person_canonical_id == StylebookPersonCanonical.id,
            )
            .join(BackfieldProject, StylebookPersonMeta.project_id == BackfieldProject.id)
            .where(StylebookPersonCanonical.stylebook_id == stylebook_id)
            .order_by(col(StylebookPersonMeta.id))
            .offset(offset)
            .limit(page)
        ).all()
        if not batch:
            break
        for meta, project_slug in batch:
            yield {
                "canonical_id": str(meta.stylebook_person_canonical_id),
                "project_slug": str(project_slug),
                "meta_type": meta.meta_type,
                "data_json": meta.data_json,
                "added": bool(meta.added),
                "edited": bool(meta.edited),
                "deleted": bool(meta.deleted),
            }
        offset += page


def _iter_organization_meta(session: Session, stylebook_id: int) -> Iterator[dict[str, Any]]:
    offset = 0
    page = 500
    while True:
        batch = session.exec(
            select(StylebookOrganizationMeta, BackfieldProject.slug)
            .join(
                StylebookOrganizationCanonical,
                StylebookOrganizationMeta.stylebook_organization_canonical_id
                == StylebookOrganizationCanonical.id,
            )
            .join(BackfieldProject, StylebookOrganizationMeta.project_id == BackfieldProject.id)
            .where(StylebookOrganizationCanonical.stylebook_id == stylebook_id)
            .order_by(col(StylebookOrganizationMeta.id))
            .offset(offset)
            .limit(page)
        ).all()
        if not batch:
            break
        for meta, project_slug in batch:
            yield {
                "canonical_id": str(meta.stylebook_organization_canonical_id),
                "project_slug": str(project_slug),
                "meta_type": meta.meta_type,
                "data_json": meta.data_json,
                "added": bool(meta.added),
                "edited": bool(meta.edited),
                "deleted": bool(meta.deleted),
            }
        offset += page


def _iter_stylebook_connections(
    session: Session,
    *,
    organization_id: int,
    location_ids: set[str],
    person_ids: set[str],
    organization_ids: set[str],
) -> Iterator[dict[str, Any]]:
    projects = session.exec(
        select(BackfieldProject).where(BackfieldProject.organization_id == organization_id)
    ).all()
    project_slug_by_id = {int(p.id): str(p.slug) for p in projects if p.id is not None}
    if not project_slug_by_id:
        return
    connections = session.exec(
        select(StylebookConnection).where(
            col(StylebookConnection.project_id).in_(list(project_slug_by_id.keys()))
        )
    ).all()
    for conn in connections:
        if not _connection_belongs_to_stylebook(
            conn,
            location_ids=location_ids,
            person_ids=person_ids,
            organization_ids=organization_ids,
        ):
            continue
        project_slug = project_slug_by_id.get(int(conn.project_id))
        if not project_slug:
            continue
        yield {
            "project_slug": project_slug,
            "from_entity_type": conn.from_entity_type,
            "from_entity_id": str(conn.from_entity_id),
            "to_entity_type": conn.to_entity_type,
            "to_entity_id": str(conn.to_entity_id),
            "nature": conn.nature,
            "description": conn.description,
            "evidence_json": conn.evidence_json,
        }


def export_stylebook_bundle(
    session: Session,
    *,
    organization_id: int,
    stylebook_id: int,
    zip_path: str | Path,
    on_progress: ProgressFn | None = None,
    rows_per_shard: int = ROWS_PER_SHARD,
) -> dict[str, Any]:
    """Write a ZIP bundle for one stylebook. Returns manifest dict."""
    sb = session.get(Stylebook, stylebook_id)
    if sb is None or int(sb.organization_id) != organization_id:
        raise StylebookLibraryError("stylebook not found")

    file_entries: list[dict[str, Any]] = []
    project_slices_by_slug: dict[str, dict[str, Any]] = {}

    def note_project(project_slug: str) -> None:
        slug = project_slug.strip()
        if slug and slug not in project_slices_by_slug:
            project = session.exec(
                select(BackfieldProject).where(BackfieldProject.slug == slug)
            ).first()
            project_slices_by_slug[slug] = {
                "project_slug": slug,
                "project_name": str(project.name) if project is not None else slug,
            }

    def prog(payload: dict[str, Any]) -> None:
        if on_progress:
            on_progress(payload)

    location_ids, person_ids, organization_ids = _stylebook_canonical_id_sets(session, stylebook_id)

    with tempfile.TemporaryDirectory(prefix="stylebook-bundle-export-") as tmp:
        work = Path(tmp)

        prog({"phase": "canonical_locations"})
        location_files = _write_jsonl_shards(
            work,
            "canonicals/locations",
            (
                location_canonical_to_export_dict(c)
                for c in _iter_location_canonicals(session, stylebook_id)
            ),
            kind=BUNDLE_KIND_LOCATION,
            project_slug=None,
            rows_per_shard=rows_per_shard,
        )
        file_entries.extend(location_files)

        prog({"phase": "canonical_people"})
        person_files = _write_jsonl_shards(
            work,
            "canonicals/people",
            (
                person_canonical_to_export_dict(c)
                for c in _iter_person_canonicals(session, stylebook_id)
            ),
            kind=BUNDLE_KIND_PERSON,
            project_slug=None,
            rows_per_shard=rows_per_shard,
        )
        file_entries.extend(person_files)

        prog({"phase": "canonical_organizations"})
        organization_files = _write_jsonl_shards(
            work,
            "canonicals/organizations",
            (
                organization_canonical_to_export_dict(c)
                for c in _iter_organization_canonicals(session, stylebook_id)
            ),
            kind=BUNDLE_KIND_ORGANIZATION,
            project_slug=None,
            rows_per_shard=rows_per_shard,
        )
        file_entries.extend(organization_files)

        prog({"phase": "aliases"})
        file_entries.extend(
            _write_jsonl_shards(
                work,
                "aliases/locations",
                _iter_location_aliases(session, stylebook_id),
                kind=BUNDLE_KIND_ALIAS_LOCATION,
                project_slug=None,
                rows_per_shard=rows_per_shard,
            )
        )
        file_entries.extend(
            _write_jsonl_shards(
                work,
                "aliases/people",
                _iter_person_aliases(session, stylebook_id),
                kind=BUNDLE_KIND_ALIAS_PERSON,
                project_slug=None,
                rows_per_shard=rows_per_shard,
            )
        )
        file_entries.extend(
            _write_jsonl_shards(
                work,
                "aliases/organizations",
                _iter_organization_aliases(session, stylebook_id),
                kind=BUNDLE_KIND_ALIAS_ORGANIZATION,
                project_slug=None,
                rows_per_shard=rows_per_shard,
            )
        )

        prog({"phase": "meta"})
        for row in _iter_location_meta(session, stylebook_id):
            note_project(str(row["project_slug"]))
        for row in _iter_person_meta(session, stylebook_id):
            note_project(str(row["project_slug"]))
        for row in _iter_organization_meta(session, stylebook_id):
            note_project(str(row["project_slug"]))
        file_entries.extend(
            _write_jsonl_shards(
                work,
                "meta/locations",
                _iter_location_meta(session, stylebook_id),
                kind=BUNDLE_KIND_META_LOCATION,
                project_slug=None,
                rows_per_shard=rows_per_shard,
            )
        )
        file_entries.extend(
            _write_jsonl_shards(
                work,
                "meta/people",
                _iter_person_meta(session, stylebook_id),
                kind=BUNDLE_KIND_META_PERSON,
                project_slug=None,
                rows_per_shard=rows_per_shard,
            )
        )
        file_entries.extend(
            _write_jsonl_shards(
                work,
                "meta/organizations",
                _iter_organization_meta(session, stylebook_id),
                kind=BUNDLE_KIND_META_ORGANIZATION,
                project_slug=None,
                rows_per_shard=rows_per_shard,
            )
        )

        prog({"phase": "connections"})
        connection_rows = list(
            _iter_stylebook_connections(
                session,
                organization_id=organization_id,
                location_ids=location_ids,
                person_ids=person_ids,
                organization_ids=organization_ids,
            )
        )
        for row in connection_rows:
            note_project(str(row["project_slug"]))
        file_entries.extend(
            _write_jsonl_shards(
                work,
                "connections",
                iter(connection_rows),
                kind=BUNDLE_KIND_CONNECTION,
                project_slug=None,
                rows_per_shard=rows_per_shard,
            )
        )

        manifest: dict[str, Any] = {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "exported_at": datetime.now(UTC).isoformat(),
            "source_organization_id": organization_id,
            "source_stylebook": {
                "id": int(stylebook_id),
                "name": str(sb.name),
                "slug": str(sb.slug),
            },
            "files": list(file_entries),
            "project_slices": sorted(
                project_slices_by_slug.values(),
                key=lambda item: str(item.get("project_slug") or ""),
            ),
        }
        manifest_path = work / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        man_body = manifest_path.read_bytes()
        all_files: list[dict[str, Any]] = [
            {
                "path": "manifest.json",
                "kind": "manifest",
                "rows": 1,
                "sha256": hashlib.sha256(man_body).hexdigest(),
            },
            *file_entries,
        ]
        manifest["files"] = all_files
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        out = Path(zip_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(manifest_path, arcname="manifest.json")
            for fe in file_entries:
                p = fe["path"]
                fp = work / p
                zf.write(fp, arcname=p)

        prog({"phase": "done", "zip_path": str(out)})
        return read_manifest_from_zip(out)


def _bundle_root_prefix_from_zip(zf: zipfile.ZipFile) -> str:
    """Return ``''`` if ``manifest.json`` is at the ZIP root.

    Otherwise return ``'{folder}/'`` when there is exactly one nested ``manifest.json``.

    Some external tools wrap the bundle in a single top-level directory (e.g. export job id).
    """
    names: list[str] = []
    for raw in zf.namelist():
        n = raw.replace("\\", "/").strip("/")
        if n:
            names.append(n)
    if not names:
        raise ValueError("bundle zip is empty")
    if "manifest.json" in names:
        return ""
    manifest_paths = [n for n in names if n.endswith("manifest.json")]
    if not manifest_paths:
        raise ValueError("bundle is missing manifest.json")
    if len(manifest_paths) > 1:
        raise ValueError(
            "bundle contains multiple manifest.json paths; expected one bundle root or a "
            "single nested folder",
        )
    path = manifest_paths[0]
    prefix = path[: -len("manifest.json")]
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"
    return prefix


def _zip_member_path(prefix: str, relative_path: str) -> str:
    rel = relative_path.replace("\\", "/").lstrip("/")
    if not prefix:
        return rel
    return f"{prefix}{rel}".replace("//", "/")


def read_manifest_from_zip(zip_path: str | Path) -> dict[str, Any]:
    """Load and validate manifest.json from a bundle ZIP."""
    zp = Path(zip_path)
    with zipfile.ZipFile(zp, "r") as zf:
        prefix = _bundle_root_prefix_from_zip(zf)
        manifest_member = _zip_member_path(prefix, "manifest.json")
        try:
            raw = zf.read(manifest_member)
        except KeyError as e:
            raise ValueError("bundle is missing manifest.json") from e
    manifest = json.loads(raw.decode("utf-8"))
    ver = manifest.get("schema_version")
    if ver not in ALLOWED_MANIFEST_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported bundle schema_version: {ver!r}")
    if not isinstance(manifest.get("files"), list):
        raise ValueError("bundle manifest missing files list")
    return manifest


def validate_zip_size(path: str | Path, *, max_bytes: int = DEFAULT_MAX_ZIP_BYTES) -> None:
    sz = Path(path).stat().st_size
    if sz > max_bytes:
        raise ValueError("bundle file is too large")


def _open_manifest_shard(zf: zipfile.ZipFile, prefix: str, rel_path: str) -> Any:
    member = _zip_member_path(prefix, rel_path)
    try:
        return zf.open(member)
    except KeyError:
        return zf.open(rel_path)


def _resolve_project_id_map(
    session: Session,
    *,
    organization_id: int,
    manifest: dict[str, Any],
    project_mappings: dict[str, int] | None,
) -> dict[str, int]:
    out: dict[str, int] = {}
    if project_mappings:
        for slug, pid in project_mappings.items():
            project = session.get(BackfieldProject, int(pid))
            if project is not None and int(project.organization_id) == organization_id:
                out[str(slug).strip()] = int(pid)
    for slice_row in manifest.get("project_slices") or []:
        if not isinstance(slice_row, dict):
            continue
        slug = str(slice_row.get("project_slug") or "").strip()
        if not slug or slug in out:
            continue
        project = session.exec(
            select(BackfieldProject).where(
                BackfieldProject.organization_id == organization_id,
                BackfieldProject.slug == slug,
            )
        ).first()
        if project is not None and project.id is not None:
            out[slug] = int(project.id)
    return out


def _remap_canonical_id(id_map: dict[str, str], entity_id: str) -> str | None:
    return id_map.get(str(entity_id))


def _import_location_row(
    session: Session,
    *,
    new_sb_id: int,
    row: dict[str, Any],
    id_map: dict[str, str],
    stats: dict[str, Any],
) -> None:
    old_id = str(row["id"])
    slug_new = allocate_unique_canonical_slug(
        session,
        stylebook_id=new_sb_id,
        label=str(row.get("label") or ""),
    )
    canon = StylebookLocationCanonical(
        stylebook_id=new_sb_id,
        label=str(row["label"]),
        slug=slug_new,
        location_type=row.get("location_type"),
        formatted_address=row.get("formatted_address"),
        primary_substrate_location_id=None,
        status=str(row.get("status") or "active"),
        geometry_json=row.get("geometry_json"),
        geometry_type=row.get("geometry_type"),
        geometry=None,
        country_code=row.get("country_code"),
        subdivision_code=row.get("subdivision_code"),
        city_name=row.get("city_name"),
        district_kind=row.get("district_kind"),
        district_number=row.get("district_number"),
        district_key=row.get("district_key"),
    )
    session.add(canon)
    session.flush()
    id_map[old_id] = str(canon.id)
    stats["canonical_locations"] += 1


def _import_person_row(
    session: Session,
    *,
    new_sb_id: int,
    row: dict[str, Any],
    id_map: dict[str, str],
    stats: dict[str, Any],
) -> None:
    old_id = str(row["id"])
    label = str(row["label"])
    slug_new = allocate_unique_person_canonical_slug(
        session,
        stylebook_id=new_sb_id,
        label=label,
    )
    sort_key_raw = row.get("sort_key")
    sort_key = (
        str(sort_key_raw).strip()
        if sort_key_raw is not None and str(sort_key_raw).strip()
        else derive_person_sort_key(label)
    )
    public_figure = row.get("public_figure")
    if not isinstance(public_figure, bool):
        public_figure = bool(public_figure) if public_figure is not None else False
    canon = StylebookPersonCanonical(
        stylebook_id=new_sb_id,
        label=label,
        slug=slug_new,
        title=row.get("title"),
        affiliation=row.get("affiliation"),
        public_figure=public_figure,
        person_type=row.get("person_type"),
        sort_key=sort_key,
        primary_substrate_person_id=None,
        status=str(row.get("status") or "active"),
    )
    session.add(canon)
    session.flush()
    id_map[old_id] = str(canon.id)
    stats["canonical_people"] += 1


def _import_organization_row(
    session: Session,
    *,
    new_sb_id: int,
    row: dict[str, Any],
    id_map: dict[str, str],
    stats: dict[str, Any],
) -> None:
    old_id = str(row["id"])
    label = str(row["label"])
    slug_new = allocate_unique_organization_canonical_slug(
        session,
        stylebook_id=new_sb_id,
        label=label,
    )
    canon = StylebookOrganizationCanonical(
        stylebook_id=new_sb_id,
        label=label,
        slug=slug_new,
        organization_type=row.get("organization_type"),
        primary_substrate_organization_id=None,
        status=str(row.get("status") or "active"),
    )
    session.add(canon)
    session.flush()
    id_map[old_id] = str(canon.id)
    stats["canonical_organizations"] += 1


def _import_location_alias_row(
    session: Session,
    *,
    row: dict[str, Any],
    id_map: dict[str, str],
    stats: dict[str, Any],
) -> None:
    new_cid = _remap_canonical_id(id_map, str(row["canonical_id"]))
    if new_cid is None:
        return
    session.add(
        StylebookLocationAlias(
            location_canonical_id=new_cid,
            alias_text=str(row["alias_text"]),
            normalized_alias=str(row["normalized_alias"]),
            provenance=str(row.get("provenance") or BUNDLE_IMPORT_PROVENANCE),
            suppressed=bool(row.get("suppressed")),
        )
    )
    stats["aliases"] += 1


def _import_person_alias_row(
    session: Session,
    *,
    row: dict[str, Any],
    id_map: dict[str, str],
    stats: dict[str, Any],
) -> None:
    new_cid = _remap_canonical_id(id_map, str(row["canonical_id"]))
    if new_cid is None:
        return
    session.add(
        StylebookPersonAlias(
            person_canonical_id=new_cid,
            alias_text=str(row["alias_text"]),
            normalized_alias=str(row["normalized_alias"]),
            provenance=str(row.get("provenance") or BUNDLE_IMPORT_PROVENANCE),
            suppressed=bool(row.get("suppressed")),
        )
    )
    stats["aliases"] += 1


def _import_organization_alias_row(
    session: Session,
    *,
    row: dict[str, Any],
    id_map: dict[str, str],
    stats: dict[str, Any],
) -> None:
    new_cid = _remap_canonical_id(id_map, str(row["canonical_id"]))
    if new_cid is None:
        return
    session.add(
        StylebookOrganizationAlias(
            organization_canonical_id=new_cid,
            alias_text=str(row["alias_text"]),
            normalized_alias=str(row["normalized_alias"]),
            provenance=str(row.get("provenance") or BUNDLE_IMPORT_PROVENANCE),
            suppressed=bool(row.get("suppressed")),
        )
    )
    stats["aliases"] += 1


def _import_location_meta_row(
    session: Session,
    *,
    row: dict[str, Any],
    id_map: dict[str, str],
    project_id_by_slug: dict[str, int],
    stats: dict[str, Any],
) -> None:
    project_slug = str(row.get("project_slug") or "").strip()
    project_id = project_id_by_slug.get(project_slug)
    new_cid = _remap_canonical_id(id_map, str(row["canonical_id"]))
    if project_id is None or new_cid is None:
        stats["skipped_meta"] += 1
        return
    session.add(
        StylebookLocationMeta(
            project_id=project_id,
            stylebook_location_canonical_id=new_cid,
            meta_type=str(row["meta_type"]),
            data_json=row.get("data_json"),
            added=bool(row.get("added")),
            edited=bool(row.get("edited")),
            deleted=bool(row.get("deleted")),
        )
    )
    stats["meta"] += 1


def _import_person_meta_row(
    session: Session,
    *,
    row: dict[str, Any],
    id_map: dict[str, str],
    project_id_by_slug: dict[str, int],
    stats: dict[str, Any],
) -> None:
    project_slug = str(row.get("project_slug") or "").strip()
    project_id = project_id_by_slug.get(project_slug)
    new_cid = _remap_canonical_id(id_map, str(row["canonical_id"]))
    if project_id is None or new_cid is None:
        stats["skipped_meta"] += 1
        return
    session.add(
        StylebookPersonMeta(
            project_id=project_id,
            stylebook_person_canonical_id=new_cid,
            meta_type=str(row["meta_type"]),
            data_json=row.get("data_json"),
            added=bool(row.get("added")),
            edited=bool(row.get("edited")),
            deleted=bool(row.get("deleted")),
        )
    )
    stats["meta"] += 1


def _import_organization_meta_row(
    session: Session,
    *,
    row: dict[str, Any],
    id_map: dict[str, str],
    project_id_by_slug: dict[str, int],
    stats: dict[str, Any],
) -> None:
    project_slug = str(row.get("project_slug") or "").strip()
    project_id = project_id_by_slug.get(project_slug)
    new_cid = _remap_canonical_id(id_map, str(row["canonical_id"]))
    if project_id is None or new_cid is None:
        stats["skipped_meta"] += 1
        return
    session.add(
        StylebookOrganizationMeta(
            project_id=project_id,
            stylebook_organization_canonical_id=new_cid,
            meta_type=str(row["meta_type"]),
            data_json=row.get("data_json"),
            added=bool(row.get("added")),
            edited=bool(row.get("edited")),
            deleted=bool(row.get("deleted")),
        )
    )
    stats["meta"] += 1


def _import_connection_row(
    session: Session,
    *,
    row: dict[str, Any],
    id_map: dict[str, str],
    project_id_by_slug: dict[str, int],
    stats: dict[str, Any],
) -> None:
    project_slug = str(row.get("project_slug") or "").strip()
    project_id = project_id_by_slug.get(project_slug)
    from_id = _remap_canonical_id(id_map, str(row["from_entity_id"]))
    to_id = _remap_canonical_id(id_map, str(row["to_entity_id"]))
    if project_id is None or from_id is None or to_id is None:
        stats["skipped_connections"] += 1
        return
    session.add(
        StylebookConnection(
            project_id=project_id,
            from_entity_type=str(row["from_entity_type"]),
            from_entity_id=from_id,
            to_entity_type=str(row["to_entity_type"]),
            to_entity_id=to_id,
            nature=row.get("nature"),
            description=row.get("description"),
            evidence_json=row.get("evidence_json"),
        )
    )
    stats["connections"] += 1


def _import_shard_rows(
    session: Session,
    *,
    kind: str,
    fh: Any,
    new_sb_id: int,
    id_map: dict[str, str],
    project_id_by_slug: dict[str, int],
    stats: dict[str, Any],
) -> None:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if kind in (BUNDLE_KIND_LEGACY_LOCATION, BUNDLE_KIND_LOCATION):
            _import_location_row(session, new_sb_id=new_sb_id, row=row, id_map=id_map, stats=stats)
        elif kind == BUNDLE_KIND_PERSON:
            _import_person_row(session, new_sb_id=new_sb_id, row=row, id_map=id_map, stats=stats)
        elif kind == BUNDLE_KIND_ORGANIZATION:
            _import_organization_row(
                session, new_sb_id=new_sb_id, row=row, id_map=id_map, stats=stats
            )
        elif kind == BUNDLE_KIND_ALIAS_LOCATION:
            _import_location_alias_row(session, row=row, id_map=id_map, stats=stats)
        elif kind == BUNDLE_KIND_ALIAS_PERSON:
            _import_person_alias_row(session, row=row, id_map=id_map, stats=stats)
        elif kind == BUNDLE_KIND_ALIAS_ORGANIZATION:
            _import_organization_alias_row(session, row=row, id_map=id_map, stats=stats)
        elif kind == BUNDLE_KIND_META_LOCATION:
            _import_location_meta_row(
                session,
                row=row,
                id_map=id_map,
                project_id_by_slug=project_id_by_slug,
                stats=stats,
            )
        elif kind == BUNDLE_KIND_META_PERSON:
            _import_person_meta_row(
                session,
                row=row,
                id_map=id_map,
                project_id_by_slug=project_id_by_slug,
                stats=stats,
            )
        elif kind == BUNDLE_KIND_META_ORGANIZATION:
            _import_organization_meta_row(
                session,
                row=row,
                id_map=id_map,
                project_id_by_slug=project_id_by_slug,
                stats=stats,
            )
        elif kind == BUNDLE_KIND_CONNECTION:
            _import_connection_row(
                session,
                row=row,
                id_map=id_map,
                project_id_by_slug=project_id_by_slug,
                stats=stats,
            )


def _seed_missing_primary_aliases(session: Session, *, stylebook_id: int) -> None:
    for canon in session.exec(
        select(StylebookLocationCanonical).where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
        )
    ).all():
        if canon.id is None:
            continue
        existing = session.exec(
            select(StylebookLocationAlias.id).where(
                StylebookLocationAlias.location_canonical_id == str(canon.id),
            )
        ).first()
        if existing is None:
            seed_aliases_for_canonical_label(
                session,
                canon_id=str(canon.id),
                label=str(canon.label),
                provenance=BUNDLE_IMPORT_PROVENANCE,
            )

    for canon in session.exec(
        select(StylebookPersonCanonical).where(
            StylebookPersonCanonical.stylebook_id == stylebook_id,
        )
    ).all():
        if canon.id is None:
            continue
        existing = session.exec(
            select(StylebookPersonAlias.id).where(
                StylebookPersonAlias.person_canonical_id == str(canon.id),
            )
        ).first()
        if existing is None:
            seed_person_aliases_for_canonical_label(
                session,
                canon_id=str(canon.id),
                label=str(canon.label),
                provenance=BUNDLE_IMPORT_PROVENANCE,
            )

    for canon in session.exec(
        select(StylebookOrganizationCanonical).where(
            StylebookOrganizationCanonical.stylebook_id == stylebook_id,
        )
    ).all():
        if canon.id is None:
            continue
        existing = session.exec(
            select(StylebookOrganizationAlias.id).where(
                StylebookOrganizationAlias.organization_canonical_id == str(canon.id),
            )
        ).first()
        if existing is None:
            seed_organization_aliases_for_canonical_label(
                session,
                canon_id=str(canon.id),
                label=str(canon.label),
                provenance=BUNDLE_IMPORT_PROVENANCE,
            )


def import_stylebook_bundle(
    session: Session,
    *,
    organization_id: int,
    zip_path: str | Path,
    new_stylebook_name: str,
    on_progress: ProgressFn | None = None,
    max_zip_bytes: int = DEFAULT_MAX_ZIP_BYTES,
    project_mappings: dict[str, int] | None = None,
) -> tuple[Stylebook, dict[str, Any]]:
    """Import bundle into a new stylebook; remap canonical UUIDs and editorial sidecars."""
    validate_zip_size(zip_path, max_bytes=max_zip_bytes)
    manifest = read_manifest_from_zip(zip_path)

    src_org = manifest.get("source_organization_id")
    if src_org is not None and int(src_org) != organization_id:
        # Same-org round-trips only for v1 (avoid cross-tenant surprises).
        pass

    def prog(p: dict[str, Any]) -> None:
        if on_progress:
            on_progress(p)

    new_book = create_stylebook_for_import(
        session,
        organization_id=organization_id,
        desired_name=new_stylebook_name,
    )
    session.commit()
    session.refresh(new_book)
    new_sb_id = int(new_book.id)  # type: ignore[arg-type]

    stats: dict[str, Any] = {
        "canonical_locations": 0,
        "canonical_people": 0,
        "canonical_organizations": 0,
        "aliases": 0,
        "meta": 0,
        "connections": 0,
        "skipped_meta": 0,
        "skipped_connections": 0,
    }
    id_map: dict[str, str] = {}
    project_id_by_slug = _resolve_project_id_map(
        session,
        organization_id=organization_id,
        manifest=manifest,
        project_mappings=project_mappings,
    )

    importable_kinds = CANONICAL_KINDS | ALIAS_KINDS | META_KINDS | {BUNDLE_KIND_CONNECTION}
    import_order = [
        *CANONICAL_KINDS,
        *ALIAS_KINDS,
        *META_KINDS,
        BUNDLE_KIND_CONNECTION,
    ]

    prog({"phase": "canonicals"})
    with zipfile.ZipFile(Path(zip_path), "r") as zf:
        prefix = _bundle_root_prefix_from_zip(zf)
        files_by_kind: dict[str, list[dict[str, Any]]] = {}
        for fe in manifest["files"]:
            kind = fe.get("kind")
            if kind not in importable_kinds:
                continue
            files_by_kind.setdefault(str(kind), []).append(fe)
        for kind in import_order:
            for fe in files_by_kind.get(kind, []):
                rel = str(fe["path"])
                with _open_manifest_shard(zf, prefix, rel) as fh:
                    _import_shard_rows(
                        session,
                        kind=kind,
                        fh=fh,
                        new_sb_id=new_sb_id,
                        id_map=id_map,
                        project_id_by_slug=project_id_by_slug,
                        stats=stats,
                    )
        session.commit()

    _seed_missing_primary_aliases(session, stylebook_id=new_sb_id)
    session.commit()

    stats["canonicals"] = (
        stats["canonical_locations"]
        + stats["canonical_people"]
        + stats["canonical_organizations"]
    )
    prog({"phase": "done", "stylebook_id": new_sb_id})
    return new_book, stats
