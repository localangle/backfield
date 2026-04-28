"""Stylebook import endpoints (GeoJSON/CSV; locations GeoJSON first)."""

from __future__ import annotations

from typing import Any

from backfield_auth.gate import require_project_access
from backfield_db import BackfieldProject
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from stylebook_api.deps import get_auth, get_session

router = APIRouter(prefix="/v1/import", tags=["import"])


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


@router.post("/geojson/analyze", response_model=AnalyzeGeoJSONResponse)
def analyze_geojson(
    project_slug: str = Query(...),
    payload: ImportGeoJSONAnalyzeRequest = Body(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> AnalyzeGeoJSONResponse:
    """Analyze GeoJSON properties to power mapping UX."""
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))

    gj = payload.geojson
    if not isinstance(gj, dict) or gj.get("type") != "FeatureCollection":
        raise HTTPException(status_code=400, detail="geojson must be a FeatureCollection")
    features = gj.get("features")
    if not isinstance(features, list):
        raise HTTPException(status_code=400, detail="geojson.features must be an array")
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

