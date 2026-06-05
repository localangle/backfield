"""Stylebook import endpoints (GeoJSON/CSV; locations GeoJSON first)."""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from typing import Any

from backfield_auth.gate import require_project_access
from backfield_db import StylebookLocationMeta
from backfield_entities.entities.location.persist import create_standalone_canonical
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlmodel import Session

from stylebook_api.catalog_scope import StylebookSlugQuery
from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.meta_utils import validate_meta_json
from stylebook_api.helpers.project_scope import (
    project_by_slug as _project_by_slug,
)
from stylebook_api.helpers.project_scope import (
    require_stylebook_id as _require_stylebook_id,
)
from stylebook_api.imports.csv_models import (
    AnalyzeCsvResponse,
    ImportCsvAnalyzeRequest,
    ImportCsvRequest,
    ImportCsvResponse,
)
from stylebook_api.imports.csv_people import CsvPeopleImporter
from stylebook_api.imports.registry import get_importer, register_importer
from stylebook_api.stylebook_permissions import require_stylebook_edit_access
from stylebook_api.stylebook_scope import require_stylebook_by_slug_in_auth_org

router = APIRouter(prefix="/v1/import", tags=["import"])
stylebook_router = APIRouter(prefix="/v1/stylebooks", tags=["import"])

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


class ImportGeoJsonMetaPropertyMapping(BaseModel):
    """Maps one GeoJSON ``properties`` key to a ``StylebookLocationMeta.meta_type``."""

    meta_type: str
    property_key: str


class ImportGeoJSONRequest(BaseModel):
    geojson: dict[str, Any]
    mappings: ImportGeoJSONFieldMappings = ImportGeoJSONFieldMappings()
    meta_property_mappings: list[ImportGeoJsonMetaPropertyMapping] = Field(default_factory=list)


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


class _ImportMetaJsonError(Exception):
    """Non-HTTP error for invalid meta payloads inside per-feature import (becomes a failed row)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _property_keys_union_from_features(
    exploded_features: list[dict[str, Any]],
) -> set[str]:
    keys: set[str] = set()
    for feat in exploded_features:
        props = feat.get("properties")
        if isinstance(props, dict):
            for k in props.keys():
                if isinstance(k, str):
                    keys.add(k)
    return keys


def _normalize_and_validate_meta_mappings_or_400(
    raw: list[ImportGeoJsonMetaPropertyMapping],
    *,
    allowed_keys: set[str],
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for i, m in enumerate(raw):
        mt = (m.meta_type or "").strip()
        pk = (m.property_key or "").strip()
        if not mt:
            raise HTTPException(
                status_code=400,
                detail=f"meta_property_mappings[{i}].meta_type must be non-empty",
            )
        if not pk:
            raise HTTPException(
                status_code=400,
                detail=f"meta_property_mappings[{i}].property_key must be non-empty",
            )
        if pk not in allowed_keys:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"meta_property_mappings[{i}].property_key {pk!r} "
                    "is not present on any feature in this GeoJSON"
                ),
            )
        out.append((mt, pk))
    return out


def _meta_value_skipped_as_empty(raw: Any) -> bool:
    if raw is None:
        return True
    if isinstance(raw, str) and not raw.strip():
        return True
    return False


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
        stylebook_slug: str | None,
        payload: ImportGeoJSONRequest,
        request: Request,
        session: Session,
        auth: dict[str, Any],
    ) -> ImportGeoJSONResponse:
        _enforce_request_size_limit(
            request,
            approx_payload={
                "geojson": payload.geojson,
                "mappings": payload.mappings.model_dump(),
                "meta_property_mappings": [m.model_dump() for m in payload.meta_property_mappings],
            },
        )
        proj = _project_by_slug(session, project_slug)
        require_project_access(session, auth, int(proj.id))
        stylebook_id = _require_stylebook_id(session, proj, stylebook_slug)

        gj = payload.geojson
        if not isinstance(gj, dict) or gj.get("type") != "FeatureCollection":
            raise HTTPException(status_code=400, detail="geojson must be a FeatureCollection")
        features = gj.get("features")
        if not isinstance(features, list):
            raise HTTPException(status_code=400, detail="geojson.features must be an array")
        exploded_features = _explode_geometry_collections(features)

        allowed_prop_keys = _property_keys_union_from_features(exploded_features)
        normalized_meta = _normalize_and_validate_meta_mappings_or_400(
            payload.meta_property_mappings,
            allowed_keys=allowed_prop_keys,
        )

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
                    canon_id = str(canon.id)
                    project_id = int(proj.id)
                    for mt, pk in normalized_meta:
                        raw_val = props.get(pk)
                        if _meta_value_skipped_as_empty(raw_val):
                            continue
                        # Single-key object so catalog UI shows Key / Value (property name → value).
                        data_payload: dict[str, Any] = {pk: raw_val}
                        try:
                            validate_meta_json(data_payload)
                        except HTTPException as exc:
                            raise _ImportMetaJsonError(str(exc.detail)) from exc
                        session.add(
                            StylebookLocationMeta(
                                project_id=project_id,
                                stylebook_location_canonical_id=canon_id,
                                meta_type=mt,
                                data_json=data_payload,
                                added=True,
                                created_at=datetime.now(UTC),
                            )
                        )
                    session.flush()
                    created.append(
                        ImportGeoJSONCreatedRow(
                            feature_index=i,
                            canonical_id=canon_id,
                            label=str(canon.label),
                        )
                    )
            except _ImportMetaJsonError as e:
                failed.append(ImportGeoJSONFailedRow(feature_index=i, error=e.message))
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
register_importer(CsvPeopleImporter())


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


@stylebook_router.post(
    "/{stylebook_slug}/import/geojson/analyze",
    response_model=AnalyzeGeoJSONResponse,
)
def analyze_geojson_stylebook(
    stylebook_slug: str,
    payload: ImportGeoJSONAnalyzeRequest = Body(...),
    request: Request = None,  # type: ignore[assignment]
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> AnalyzeGeoJSONResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    if request is None:
        raise HTTPException(status_code=500, detail="request missing")
    _enforce_request_size_limit(request, approx_payload=payload.geojson)
    _ = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)

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
    stylebook_slug: StylebookSlugQuery = None,
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
        stylebook_slug=stylebook_slug,
        payload=payload,
        request=request,
        session=session,
        auth=auth,
    )


@stylebook_router.post(
    "/{stylebook_slug}/import/geojson",
    response_model=ImportGeoJSONResponse,
)
def import_geojson_stylebook(
    stylebook_slug: str,
    payload: ImportGeoJSONRequest = Body(...),
    request: Request = None,  # type: ignore[assignment]
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ImportGeoJSONResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    if request is None:
        raise HTTPException(status_code=500, detail="request missing")
    _enforce_request_size_limit(
        request,
        approx_payload={
            "geojson": payload.geojson,
            "mappings": payload.mappings.model_dump(),
            "meta_property_mappings": [m.model_dump() for m in payload.meta_property_mappings],
        },
    )
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    stylebook_id = int(sb.id)

    gj = payload.geojson
    if not isinstance(gj, dict) or gj.get("type") != "FeatureCollection":
        raise HTTPException(status_code=400, detail="geojson must be a FeatureCollection")
    features = gj.get("features")
    if not isinstance(features, list):
        raise HTTPException(status_code=400, detail="geojson.features must be an array")
    exploded_features = _explode_geometry_collections(features)

    allowed_prop_keys = _property_keys_union_from_features(exploded_features)
    _ = _normalize_and_validate_meta_mappings_or_400(
        payload.meta_property_mappings,
        allowed_keys=allowed_prop_keys,
    )

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
                ImportGeoJSONFailedRow(feature_index=i, error="feature.type must be Feature")
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
            failed.append(ImportGeoJSONFailedRow(feature_index=i, error="name/label is required"))
            continue
        if not location_type:
            failed.append(ImportGeoJSONFailedRow(feature_index=i, error="type is required"))
            continue
        if geometry_json is None:
            failed.append(ImportGeoJSONFailedRow(feature_index=i, error="geometry is required"))
            continue

        with contextlib.suppress(Exception):
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
        except Exception as e:  # noqa: BLE001 - per-row boundary
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


@stylebook_router.post(
    "/{stylebook_slug}/import/csv/people/analyze",
    response_model=AnalyzeCsvResponse,
)
def analyze_csv_people_stylebook(
    stylebook_slug: str,
    payload: ImportCsvAnalyzeRequest = Body(...),
    request: Request = None,  # type: ignore[assignment]
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> AnalyzeCsvResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    if request is None:
        raise HTTPException(status_code=500, detail="request missing")
    _enforce_request_size_limit(request, approx_payload={"csv_data": payload.csv_data})
    _ = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    imp = get_importer("csv", "people")
    return imp.analyze(payload=payload, request=request)


@stylebook_router.post(
    "/{stylebook_slug}/import/csv/people",
    response_model=ImportCsvResponse,
)
def import_csv_people_stylebook(
    stylebook_slug: str,
    payload: ImportCsvRequest = Body(...),
    request: Request = None,  # type: ignore[assignment]
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> ImportCsvResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    if request is None:
        raise HTTPException(status_code=500, detail="request missing")
    _enforce_request_size_limit(request, approx_payload={"csv_data": payload.csv_data})
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    imp = get_importer("csv", "people")
    return imp.run(
        stylebook_id=int(sb.id),
        payload=payload,
        session=session,
        request=request,
    )

