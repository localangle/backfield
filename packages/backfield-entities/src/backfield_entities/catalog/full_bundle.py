"""Full stylebook ZIP export/import (manifest + sharded JSONL).

See docs/OPERATIONS.md for S3 staging env vars used by the worker/API.
Entity-type catalog create/import/export checklist: docs/ENTITY_TYPES.md.
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
    Stylebook,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
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
# v3: per-entity shards under ``canonicals/{entity}/`` with kinds ``canonical_location``,
# ``canonical_person``, … (see docs/ENTITY_TYPES.md → Stylebook catalog transfer).
BUNDLE_SCHEMA_VERSION = 3
ALLOWED_MANIFEST_SCHEMA_VERSIONS = frozenset({1, 2, 3})
BUNDLE_KIND_LEGACY_LOCATION = "canonical"
BUNDLE_KIND_LOCATION = "canonical_location"
BUNDLE_KIND_PERSON = "canonical_person"
BUNDLE_KIND_ORGANIZATION = "canonical_organization"
ROWS_PER_SHARD = 2000
DEFAULT_MAX_ZIP_BYTES = 512 * 1024 * 1024  # 512 MiB guardrail

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

    def prog(payload: dict[str, Any]) -> None:
        if on_progress:
            on_progress(payload)

    with tempfile.TemporaryDirectory(prefix="stylebook-bundle-export-") as tmp:
        work = Path(tmp)

        prog({"phase": "canonical_locations"})
        location_rows = (
            location_canonical_to_export_dict(c)
            for c in _iter_location_canonicals(session, stylebook_id)
        )
        location_files = _write_jsonl_shards(
            work,
            "canonicals/locations",
            location_rows,
            kind=BUNDLE_KIND_LOCATION,
            project_slug=None,
            rows_per_shard=rows_per_shard,
        )
        file_entries.extend(location_files)

        prog({"phase": "canonical_people"})
        person_rows = (
            person_canonical_to_export_dict(c)
            for c in _iter_person_canonicals(session, stylebook_id)
        )
        person_files = _write_jsonl_shards(
            work,
            "canonicals/people",
            person_rows,
            kind=BUNDLE_KIND_PERSON,
            project_slug=None,
            rows_per_shard=rows_per_shard,
        )
        file_entries.extend(person_files)

        prog({"phase": "canonical_organizations"})
        organization_rows = (
            organization_canonical_to_export_dict(c)
            for c in _iter_organization_canonicals(session, stylebook_id)
        )
        organization_files = _write_jsonl_shards(
            work,
            "canonicals/organizations",
            organization_rows,
            kind=BUNDLE_KIND_ORGANIZATION,
            project_slug=None,
            rows_per_shard=rows_per_shard,
        )
        file_entries.extend(organization_files)

        project_slices: list[dict[str, Any]] = []

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
            "project_slices": project_slices,
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
    cid = str(canon.id)
    seed_aliases_for_canonical_label(
        session,
        canon_id=cid,
        label=str(row.get("label") or ""),
        provenance="stylebook_bundle_import",
    )
    id_map[old_id] = cid
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
    cid = str(canon.id)
    seed_person_aliases_for_canonical_label(
        session,
        canon_id=cid,
        label=label,
        provenance="stylebook_bundle_import",
    )
    id_map[old_id] = cid
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
    cid = str(canon.id)
    seed_organization_aliases_for_canonical_label(
        session,
        canon_id=cid,
        label=label,
        provenance="stylebook_bundle_import",
    )
    id_map[old_id] = cid
    stats["canonical_organizations"] += 1


def _import_shard_rows(
    session: Session,
    *,
    kind: str,
    fh: Any,
    new_sb_id: int,
    id_map: dict[str, str],
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


def import_stylebook_bundle(
    session: Session,
    *,
    organization_id: int,
    zip_path: str | Path,
    new_stylebook_name: str,
    on_progress: ProgressFn | None = None,
    max_zip_bytes: int = DEFAULT_MAX_ZIP_BYTES,
) -> tuple[Stylebook, dict[str, Any]]:
    """Import bundle into a new stylebook; remap canonical UUIDs (canonical rows only)."""
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
    }
    id_map: dict[str, str] = {}

    importable_kinds = {
        BUNDLE_KIND_LEGACY_LOCATION,
        BUNDLE_KIND_LOCATION,
        BUNDLE_KIND_PERSON,
        BUNDLE_KIND_ORGANIZATION,
    }

    prog({"phase": "canonicals"})
    with zipfile.ZipFile(Path(zip_path), "r") as zf:
        prefix = _bundle_root_prefix_from_zip(zf)
        for fe in manifest["files"]:
            kind = fe.get("kind")
            if kind not in importable_kinds:
                continue
            rel = str(fe["path"])
            with _open_manifest_shard(zf, prefix, rel) as fh:
                _import_shard_rows(
                    session,
                    kind=str(kind),
                    fh=fh,
                    new_sb_id=new_sb_id,
                    id_map=id_map,
                    stats=stats,
                )
        session.commit()

    stats["canonicals"] = (
        stats["canonical_locations"]
        + stats["canonical_people"]
        + stats["canonical_organizations"]
    )
    prog({"phase": "done", "stylebook_id": new_sb_id})
    return new_book, stats
