"""Stylebook import endpoints (GeoJSON/CSV; locations GeoJSON first)."""

from __future__ import annotations

import contextlib
import json
from typing import Any

from backfield_auth.gate import require_project_access
from backfield_db import BackfieldProject
from backfield_stylebook.locations import create_standalone_canonical
from backfield_stylebook.resolve import resolve_stylebook_id_for_project_id
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from stylebook_api.deps import get_auth, get_session
from stylebook_api.imports.registry import get_importer, register_importer

router = APIRouter(prefix="/v1/import", tags=["import"])

MAX_IMPORT_BYTES = 25 * 1024 * 1024


def _enforce_request_size_limit(request: Request, *, approx_payload: object | None) -> None:
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            n = int(cl)
        except ValueError:
            n = 0
        if n > MAX_IMPORT_BYTES:
            raise HTTPException(status_code=413, detail="payload exceeds 25MB")
        return
    if approx_payload is None:
        return
    try:
        n2 = len(json.dumps(approx_payload).encode("utf-8"))
    except Exception:  # noqa: BLE001 - best-effort size guard
        return
    if n2 > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="payload exceeds 25MB")

def _project_by_slug(session: Session, slug: str) -> BackfieldProject:
    row = session.exec(select(BackfieldProject).where(BackfieldProject.slug == slug)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return row


class ImportGeoJSONAnalyzeRequest(BaseModel):
    geojson: dict[str, Any]


class AnalyzeGeoJSONResponse(BaseModel):
    feature_count: int
    available_properties: list[str]
    sample_feature: dict[str, Any] | None = None


class ImportGeoJSONFieldMappings(BaseModel):
    label_property: str | None = None
    location_type_property: str | None = None
    formatted_address_property: str | None = None
    location_type_value: str | None = None


class ImportGeoJSONRequest(BaseModel):
    geojson: dict[str, Any]
    mappings: ImportGeoJSONFieldMappings = ImportGeoJSONFieldMappings()


class ImportGeoJSONCreatedRow(BaseModel):
    feature_index: int
    canonical_id: str
    label: str


class ImportGeoJSONFailedRow(BaseModel):
    feature_index: int
    error: str


class ImportGeoJSONResponse(BaseModel):
    total_features: int
    attempted_features: int
    created_count: int
    failed_count: int
    created: list[ImportGeoJSONCreatedRow]
    failed: list[ImportGeoJSONFailedRow]


class _GeoJsonLocationsImporter:
    format = "geojson"
    entity = "locations"

    def analyze(
        self,
        *,
        project_slug: str,
        payload: ImportGeoJSONAnalyzeRequest,
        request: Request,
        session: Session,
        auth: dict[str, Any],
    ) -> AnalyzeGeoJSONResponse:
        _enforce_request_size_limit(request, approx_payload=payload.geojson)
        proj = _project_by_slug(session, project_slug)
        require_project_access(session, auth, int(proj.id))

        gj = payload.geojson
        if not isinstance(gj, dict) or gj.get("type") != "FeatureCollection":
            raise HTTPException(status_code=400, detail="geojson must be a FeatureCollection")
        features = gj.get("features")
        if not isinstance(features, list):
            raise HTTPException(status_code=400, detail="geojson.features must be an array")
        features = _explode_geometry_collections(features)
        if not features:
            return AnalyzeGeoJSONResponse(
                feature_count=0,
                available_properties=[],
                sample_feature=None,
            )

        keys: set[str] = set()
        sample: dict[str, Any] | None = None

        for feat in features:
            if not isinstance(feat, dict):
                continue
            props = feat.get("properties")
            if isinstance(props, dict):
                for k in props.keys():
                    if isinstance(k, str):
                        keys.add(k)
                if sample is None and props:
                    geom = feat.get("geometry")
                    geom_type = geom.get("type") if isinstance(geom, dict) else None
                    sample = {"properties": props, "geometry_type": geom_type}

        return AnalyzeGeoJSONResponse(
            feature_count=len(features),
            available_properties=sorted(keys),
            sample_feature=sample,
        )

    def run(
        self,
        *,
        project_slug: str,
        payload: ImportGeoJSONRequest,
        request: Request,
        session: Session,
        auth: dict[str, Any],
    ) -> ImportGeoJSONResponse:
        _enforce_request_size_limit(
            request,
            approx_payload={"geojson": payload.geojson, "mappings": payload.mappings.model_dump()},
        )
        proj = _project_by_slug(session, project_slug)
        require_project_access(session, auth, int(proj.id))
        stylebook_id = _require_stylebook_id(session, proj)

        gj = payload.geojson
        if not isinstance(gj, dict) or gj.get("type") != "FeatureCollection":
            raise HTTPException(status_code=400, detail="geojson must be a FeatureCollection")
        features = gj.get("features")
        if not isinstance(features, list):
            raise HTTPException(status_code=400, detail="geojson.features must be an array")
        exploded_features = _explode_geometry_collections(features)

        mappings = payload.mappings
        label_key = mappings.label_property or "name"
        type_key = mappings.location_type_property or "type"
        addr_key = mappings.formatted_address_property or "formatted_address"
        type_override = (mappings.location_type_value or "").strip().lower() or None

        created: list[ImportGeoJSONCreatedRow] = []
        failed: list[ImportGeoJSONFailedRow] = []

        for i, feat in enumerate(exploded_features):
            if not isinstance(feat, dict):
                failed.append(
                    ImportGeoJSONFailedRow(feature_index=i, error="feature must be an object")
                )
                continue
            if feat.get("type") != "Feature":
                failed.append(
                    ImportGeoJSONFailedRow(
                        feature_index=i, error="feature.type must be Feature"
                    )
                )
                continue

            props_raw = feat.get("properties")
            props = props_raw if isinstance(props_raw, dict) else {}

            label = _read_string_prop(props, label_key)
            location_type = type_override or _read_string_prop(props, type_key)
            formatted_address = _read_string_prop(props, addr_key)

            geom_raw = feat.get("geometry")
            geometry_json = geom_raw if isinstance(geom_raw, dict) else None

            if not label:
                failed.append(
                    ImportGeoJSONFailedRow(feature_index=i, error="name/label is required")
                )
                continue
            if not location_type:
                failed.append(ImportGeoJSONFailedRow(feature_index=i, error="type is required"))
                continue
            if geometry_json is None:
                failed.append(
                    ImportGeoJSONFailedRow(feature_index=i, error="geometry is required")
                )
                continue

            with contextlib.suppress(Exception):
                # Ensure any accidental non-dict types don't leak through.
                _ = str(geometry_json.get("type"))

            try:
                with session.begin_nested():
                    canon = create_standalone_canonical(
                        session,
                        stylebook_id=stylebook_id,
                        label=label,
                        location_type=location_type,
                        formatted_address=formatted_address,
                        geometry_json=geometry_json,
                        provenance="stylebook_ui_import_geojson",
                    )
                    session.flush()
                    created.append(
                        ImportGeoJSONCreatedRow(
                            feature_index=i,
                            canonical_id=str(canon.id),
                            label=str(canon.label),
                        )
                    )
            except Exception as e:  # noqa: BLE001 - boundary layer; surface message per-row
                failed.append(ImportGeoJSONFailedRow(feature_index=i, error=str(e)))

        if created:
            session.commit()
        else:
            session.rollback()

        return ImportGeoJSONResponse(
            total_features=len(exploded_features),
            attempted_features=len(created) + len(failed),
            created_count=len(created),
            failed_count=len(failed),
            created=created,
            failed=failed,
        )


register_importer(_GeoJsonLocationsImporter())


@router.post("/geojson/analyze", response_model=AnalyzeGeoJSONResponse)
def analyze_geojson(
    project_slug: str = Query(...),
    payload: ImportGeoJSONAnalyzeRequest = Body(...),
    request: Request = None,  # type: ignore[assignment]
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> AnalyzeGeoJSONResponse:
    imp = get_importer("geojson", "locations")
    if request is None:
        raise HTTPException(status_code=500, detail="request missing")
    return imp.analyze(
        project_slug=project_slug,
        payload=payload,
        request=request,
        session=session,
        auth=auth,
    )


def _require_stylebook_id(session: Session, project: BackfieldProject) -> int:
    try:
        return resolve_stylebook_id_for_project_id(session, int(project.id))
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _read_string_prop(props: dict[str, Any], key: str | None) -> str | None:
    if not key:
        return None
    v = props.get(key)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _explode_geometry_collections(features: list[Any]) -> list[dict[str, Any]]:
    """Split GeometryCollection features into multiple Features.

    We keep `properties` as-is and replace `geometry` with each member geometry.
    """
    out: list[dict[str, Any]] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        geom = feat.get("geometry")
        if not isinstance(geom, dict) or geom.get("type") != "GeometryCollection":
            out.append(feat)
            continue
        geoms = geom.get("geometries")
        if not isinstance(geoms, list) or not geoms:
            out.append({**feat, "geometry": None})
            continue
        for g in geoms:
            if not isinstance(g, dict):
                continue
            out.append({**feat, "geometry": g})
    return out


@router.post("/geojson", response_model=ImportGeoJSONResponse)
def import_geojson(
    project_slug: str = Query(...),
    payload: ImportGeoJSONRequest = Body(...),
    request: Request = None,  # type: ignore[assignment]
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ImportGeoJSONResponse:
    imp = get_importer("geojson", "locations")
    if request is None:
        raise HTTPException(status_code=500, detail="request missing")
    return imp.run(
        project_slug=project_slug,
        payload=payload,
        request=request,
        session=session,
        auth=auth,
    )

