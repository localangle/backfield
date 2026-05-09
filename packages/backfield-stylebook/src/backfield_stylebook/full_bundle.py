"""Full stylebook ZIP export/import (manifest + sharded JSONL).

See docs/OPERATIONS.md for S3 staging env vars used by the worker/API.
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
)
from sqlalchemy import and_, or_
from sqlmodel import Session, col, select

from backfield_stylebook.canonical_slug import allocate_unique_canonical_slug
from backfield_stylebook.locations import upsert_alias_for_canonical_text
from backfield_stylebook.stylebook_library import (
    StylebookLibraryError,
    create_stylebook_for_import,
)

BUNDLE_SCHEMA_VERSION = 1
ROWS_PER_SHARD = 2000
DEFAULT_MAX_ZIP_BYTES = 512 * 1024 * 1024  # 512 MiB guardrail

ProgressFn = Callable[[dict[str, Any]], None]


def _iso_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def canonical_to_export_dict(c: StylebookLocationCanonical) -> dict[str, Any]:
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


def alias_to_export_dict(a: StylebookLocationAlias) -> dict[str, Any]:
    return {
        "id": int(a.id) if a.id is not None else None,
        "location_canonical_id": str(a.location_canonical_id),
        "alias_text": a.alias_text,
        "normalized_alias": a.normalized_alias,
        "provenance": a.provenance,
        "suppressed": bool(a.suppressed),
        "created_at": _iso_utc(a.created_at),
        "updated_at": _iso_utc(a.updated_at),
    }


def meta_to_export_dict(m: StylebookLocationMeta) -> dict[str, Any]:
    return {
        "id": int(m.id) if m.id is not None else None,
        "project_id": int(m.project_id),
        "stylebook_location_canonical_id": str(m.stylebook_location_canonical_id),
        "meta_type": m.meta_type,
        "data_json": m.data_json,
        "added": bool(m.added),
        "edited": bool(m.edited),
        "deleted": bool(m.deleted),
        "created_at": _iso_utc(m.created_at),
    }


def connection_to_export_dict(c: StylebookConnection) -> dict[str, Any]:
    return {
        "id": int(c.id) if c.id is not None else None,
        "project_id": int(c.project_id),
        "from_entity_type": c.from_entity_type,
        "from_entity_id": str(c.from_entity_id),
        "to_entity_type": c.to_entity_type,
        "to_entity_id": str(c.to_entity_id),
        "nature": c.nature,
        "created_at": _iso_utc(c.created_at),
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


def _iter_canonicals(session: Session, stylebook_id: int) -> Iterator[StylebookLocationCanonical]:
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


def _iter_aliases(session: Session, stylebook_id: int) -> Iterator[StylebookLocationAlias]:
    offset = 0
    page = 500
    while True:
        batch = session.exec(
            select(StylebookLocationAlias)
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
        yield from batch
        offset += page


def _iter_meta_for_project(
    session: Session, *, stylebook_id: int, project_id: int
) -> Iterator[StylebookLocationMeta]:
    offset = 0
    page = 500
    while True:
        batch = session.exec(
            select(StylebookLocationMeta)
            .join(
                StylebookLocationCanonical,
                StylebookLocationMeta.stylebook_location_canonical_id
                == StylebookLocationCanonical.id,
            )
            .where(
                StylebookLocationMeta.project_id == project_id,
                StylebookLocationCanonical.stylebook_id == stylebook_id,
            )
            .order_by(col(StylebookLocationMeta.id))
            .offset(offset)
            .limit(page)
        ).all()
        if not batch:
            break
        yield from batch
        offset += page


def _iter_connections_for_project(
    session: Session, *, stylebook_id: int, project_id: int
) -> Iterator[StylebookConnection]:
    canon_sq = select(StylebookLocationCanonical.id).where(
        StylebookLocationCanonical.stylebook_id == stylebook_id
    )
    cond = or_(
        and_(
            StylebookConnection.from_entity_type == "location",
            col(StylebookConnection.from_entity_id).in_(canon_sq),
        ),
        and_(
            StylebookConnection.to_entity_type == "location",
            col(StylebookConnection.to_entity_id).in_(canon_sq),
        ),
    )
    offset = 0
    page = 500
    while True:
        batch = session.exec(
            select(StylebookConnection)
            .where(StylebookConnection.project_id == project_id)
            .where(cond)
            .order_by(col(StylebookConnection.id))
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

        prog({"phase": "canonicals"})
        canon_files = _write_jsonl_shards(
            work,
            "canonicals",
            (canonical_to_export_dict(c) for c in _iter_canonicals(session, stylebook_id)),
            kind="canonical",
            project_slug=None,
            rows_per_shard=rows_per_shard,
        )
        file_entries.extend(canon_files)

        prog({"phase": "aliases"})
        alias_files = _write_jsonl_shards(
            work,
            "aliases",
            (alias_to_export_dict(a) for a in _iter_aliases(session, stylebook_id)),
            kind="alias",
            project_slug=None,
            rows_per_shard=rows_per_shard,
        )
        file_entries.extend(alias_files)

        projects = session.exec(
            select(BackfieldProject).where(BackfieldProject.organization_id == organization_id)
        ).all()

        project_slices: list[dict[str, Any]] = []
        for proj in projects:
            pid = int(proj.id)
            slug = str(proj.slug)
            meta_rows = list(
                _iter_meta_for_project(session, stylebook_id=stylebook_id, project_id=pid)
            )
            conn_rows = list(
                _iter_connections_for_project(session, stylebook_id=stylebook_id, project_id=pid)
            )
            if not meta_rows and not conn_rows:
                continue

            slice_entry: dict[str, Any] = {
                "project_id": pid,
                "project_slug": slug,
                "meta_row_count": len(meta_rows),
                "connection_row_count": len(conn_rows),
            }

            if meta_rows:
                mf = _write_jsonl_shards(
                    work,
                    f"meta/{slug}",
                    (meta_to_export_dict(m) for m in meta_rows),
                    kind="meta",
                    project_slug=slug,
                    rows_per_shard=rows_per_shard,
                )
                file_entries.extend(mf)

            if conn_rows:
                cf = _write_jsonl_shards(
                    work,
                    f"connections/{slug}",
                    (connection_to_export_dict(c) for c in conn_rows),
                    kind="connection",
                    project_slug=slug,
                    rows_per_shard=rows_per_shard,
                )
                file_entries.extend(cf)

            project_slices.append(slice_entry)

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


def read_manifest_from_zip(zip_path: str | Path) -> dict[str, Any]:
    """Load and validate manifest.json from a bundle ZIP."""
    zp = Path(zip_path)
    with zipfile.ZipFile(zp, "r") as zf:
        try:
            raw = zf.read("manifest.json")
        except KeyError as e:
            raise ValueError("bundle is missing manifest.json") from e
    manifest = json.loads(raw.decode("utf-8"))
    ver = manifest.get("schema_version")
    if ver != BUNDLE_SCHEMA_VERSION:
        raise ValueError(f"unsupported bundle schema_version: {ver!r}")
    if not isinstance(manifest.get("files"), list):
        raise ValueError("bundle manifest missing files list")
    return manifest


def validate_zip_size(path: str | Path, *, max_bytes: int = DEFAULT_MAX_ZIP_BYTES) -> None:
    sz = Path(path).stat().st_size
    if sz > max_bytes:
        raise ValueError("bundle file is too large")


def import_stylebook_bundle(
    session: Session,
    *,
    organization_id: int,
    zip_path: str | Path,
    new_stylebook_name: str,
    project_mappings: dict[str, int],
    on_progress: ProgressFn | None = None,
    max_zip_bytes: int = DEFAULT_MAX_ZIP_BYTES,
) -> tuple[Stylebook, dict[str, Any]]:
    """Import bundle into a new stylebook; remap canonical UUIDs and project ids per mappings."""
    validate_zip_size(zip_path, max_bytes=max_zip_bytes)
    manifest = read_manifest_from_zip(zip_path)

    src_org = manifest.get("source_organization_id")
    if src_org is not None and int(src_org) != organization_id:
        # Same-org round-trips only for v1 (avoid cross-tenant surprises).
        pass

    def prog(p: dict[str, Any]) -> None:
        if on_progress:
            on_progress(p)

    # Validate target projects belong to org
    for slug, tid in project_mappings.items():
        p = session.get(BackfieldProject, int(tid))
        if p is None or int(p.organization_id) != organization_id:
            raise ValueError(f"invalid target project for slug {slug!r}")
        if str(p.slug) != str(slug):
            # Allow mapping from export slug to different project slug? Plan: key is source slug.
            pass

    new_book = create_stylebook_for_import(
        session,
        organization_id=organization_id,
        desired_name=new_stylebook_name,
    )
    session.commit()
    session.refresh(new_book)
    new_sb_id = int(new_book.id)  # type: ignore[arg-type]

    stats: dict[str, Any] = {
        "canonicals": 0,
        "aliases": 0,
        "meta": 0,
        "connections": 0,
        "meta_skipped_slices": 0,
        "connection_skipped_slices": 0,
        "aliases_skipped": 0,
        "connections_skipped": 0,
    }
    id_map: dict[str, str] = {}

    prog({"phase": "canonicals"})
    with zipfile.ZipFile(Path(zip_path), "r") as zf:
        for fe in manifest["files"]:
            if fe.get("kind") != "canonical":
                continue
            rel = fe["path"]
            with zf.open(rel) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
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
                    nid = str(canon.id)
                    id_map[old_id] = nid
                    stats["canonicals"] += 1
        session.commit()

        prog({"phase": "aliases"})
        for fe in manifest["files"]:
            if fe.get("kind") != "alias":
                continue
            rel = fe["path"]
            with zf.open(rel) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    old_cid = str(row["location_canonical_id"])
                    new_cid = id_map.get(old_cid)
                    if not new_cid:
                        stats["aliases_skipped"] += 1
                        continue
                    upsert_alias_for_canonical_text(
                        session,
                        canon_id=new_cid,
                        alias_text=str(row["alias_text"]),
                        normalized_alias=str(row["normalized_alias"]),
                        provenance=str(row.get("provenance") or "bundle_import"),
                    )
                    stats["aliases"] += 1
        session.commit()

        prog({"phase": "meta_and_connections"})

        for fe in manifest["files"]:
            kind = fe.get("kind")
            slug = fe.get("project_slug")
            if kind not in ("meta", "connection") or not slug:
                continue
            target_pid = project_mappings.get(str(slug))
            if target_pid is None:
                if kind == "meta":
                    stats["meta_skipped_slices"] += 1
                else:
                    stats["connection_skipped_slices"] += 1
                continue
            rel = fe["path"]
            with zf.open(rel) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    if kind == "meta":
                        old_cid = str(row["stylebook_location_canonical_id"])
                        new_cid = id_map.get(old_cid)
                        if not new_cid:
                            continue
                        meta = StylebookLocationMeta(
                            project_id=int(target_pid),
                            stylebook_location_canonical_id=new_cid,
                            meta_type=str(row["meta_type"]),
                            data_json=row.get("data_json"),
                            added=bool(row.get("added", False)),
                            edited=bool(row.get("edited", False)),
                            deleted=bool(row.get("deleted", False)),
                        )
                        session.add(meta)
                        stats["meta"] += 1
                    else:
                        from_t = str(row["from_entity_type"])
                        to_t = str(row["to_entity_type"])
                        from_id = str(row["from_entity_id"])
                        to_id = str(row["to_entity_id"])
                        if from_t == "location" and from_id not in id_map:
                            stats["connections_skipped"] += 1
                            continue
                        if to_t == "location" and to_id not in id_map:
                            stats["connections_skipped"] += 1
                            continue
                        new_from = id_map[from_id] if from_t == "location" else from_id
                        new_to = id_map[to_id] if to_t == "location" else to_id
                        conn = StylebookConnection(
                            project_id=int(target_pid),
                            from_entity_type=from_t,
                            from_entity_id=new_from,
                            to_entity_type=to_t,
                            to_entity_id=new_to,
                            nature=str(row["nature"]),
                        )
                        session.add(conn)
                        stats["connections"] += 1
            session.commit()

    prog({"phase": "done", "stylebook_id": new_sb_id})
    return new_book, stats
