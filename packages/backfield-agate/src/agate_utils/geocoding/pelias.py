"""Pelias geocoding service wrapper."""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

import httpx
from agate_utils.geocoding.geocoding_types import (
    Confidence,
    GeocodingResult,
    GeocodingResultData,
    GeometryPoint,
    GeometryPolygon,
    bbox_west_south_east_north_to_polygon_coordinates,
)

logger = logging.getLogger(__name__)

# Geocode.Earth can be slow; connect timeouts often mean edge/network congestion, not bad params.
_PELIAS_HTTP_TIMEOUT = httpx.Timeout(60.0, connect=20.0)
_PELIAS_API_KEY_IN_URL = re.compile(r"([?&])api_key=[^&]*", re.IGNORECASE)


def _redact_pelias_url(url_str: str) -> str:
    return _PELIAS_API_KEY_IN_URL.sub(r"\1api_key=<redacted>", url_str)


def _params_for_log(params: dict[str, Any]) -> dict[str, Any]:
    """Copy params for logging without leaking ``api_key``."""
    out = dict(params)
    if "api_key" in out:
        out["api_key"] = "<redacted>"
    return out


async def _pelias_get(
    client: httpx.AsyncClient, url: str, params: dict[str, Any]
) -> httpx.Response:
    """GET with one retry on transient connect/read/pool timeouts."""
    transient = (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout)
    try:
        return await client.get(url, params=params)
    except transient as first:
        logger.warning("Pelias %s, retrying once", type(first).__name__)
        await asyncio.sleep(0.75)
        return await client.get(url, params=params)


def _pelias_http_error_suffix(exc: Exception) -> str:
    """Best-effort URL / status from httpx errors (``str(exc)`` is often empty for timeouts)."""
    chunks: list[str] = []
    request = getattr(exc, "request", None)
    if request is not None:
        try:
            url_s = _redact_pelias_url(str(request.url))
            chunks.append(f"method={request.method} url={url_s}")
        except Exception:
            chunks.append("request=<unavailable>")
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            chunks.append(f"http_status={response.status_code}")
        except Exception:
            pass
    return f" [{'; '.join(chunks)}]" if chunks else ""


def _log_pelias_exception(operation: str, exc: Exception, *, detail: str = "") -> None:
    """Log type + repr + httpx context so empty-message exceptions remain diagnosable."""
    detail_part = f" {detail}" if detail else ""
    logger.error(
        "Pelias %s failed:%s %s: %r%s",
        operation,
        detail_part,
        type(exc).__name__,
        exc,
        _pelias_http_error_suffix(exc),
        exc_info=True,
    )


def _pelias_feature_to_result(
    *,
    geocoder_name: str,
    input_str: str,
    feature: dict[str, Any],
) -> Optional[GeocodingResult]:
    """Map one Pelias GeoJSON feature to a ``GeocodingResult``.

    Notes:
    - Prefer feature-level ``bbox`` (not top-level FeatureCollection bbox).
    - Include enough Pelias metadata in ``confidence`` for model-side candidate selection.
    """
    properties = feature.get("properties", {})
    geometry = feature.get("geometry", {})
    bbox = feature.get("bbox")

    layer = properties.get("layer", "")
    is_area = layer in [
        "city",
        "county",
        "region",
        "country",
        "localadmin",
        "neighbourhood",
        "locality",
    ]

    if bbox and is_area and len(bbox) == 4:
        logger.info("Using bbox for %s: %s", layer, bbox)
        result_geometry = GeometryPolygon(
            type="Polygon",
            coordinates=bbox_west_south_east_north_to_polygon_coordinates(bbox),
        )
    else:
        if geometry.get("type") != "Point":
            logger.warning("Unexpected geometry type: %s", geometry.get("type"))
            return None

        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            logger.warning("Invalid coordinates in result")
            return None

        lon, lat = coords[0], coords[1]
        result_geometry = GeometryPoint(
            type="Point",
            coordinates=[lon, lat],
        )

    layer = properties.get("layer", "")
    if layer == "neighbourhood":
        result_id = properties.get("neighbourhood_gid")
    elif layer == "locality":
        result_id = properties.get("locality_gid")
    elif layer == "county":
        result_id = properties.get("county_gid")
    elif layer == "region":
        result_id = properties.get("region_gid")
    else:
        result_id = properties.get("gid")

    confidence: dict[str, Any] = {
        "pelias_layer": layer,
        "pelias_source": properties.get("source"),
        "pelias_source_id": properties.get("source_id"),
        "pelias_gid": properties.get("gid"),
        "pelias_accuracy": properties.get("accuracy"),
        "pelias_match_type": properties.get("match_type"),
        "pelias_confidence": properties.get("confidence"),
        "pelias_has_bbox": bool(bbox and len(bbox) == 4),
        "pelias_bbox": bbox if isinstance(bbox, list) and len(bbox) == 4 else None,
        # Useful for jurisdiction filtering in area models.
        "pelias_country_code": properties.get("country_code"),
        "pelias_country": properties.get("country"),
        "pelias_region": properties.get("region"),
        "pelias_region_a": properties.get("region_a"),
        "pelias_county": properties.get("county"),
        "pelias_locality": properties.get("locality"),
        "pelias_localadmin": properties.get("localadmin"),
        "pelias_neighbourhood": properties.get("neighbourhood"),
        "pelias_borough": properties.get("borough"),
    }

    result_data = GeocodingResultData(
        id=result_id,
        processed_str=properties.get("label", input_str),
        geometry=result_geometry,
        confidence=confidence,
    )

    return GeocodingResult(
        geocoder=geocoder_name,
        input_str=input_str,
        result=result_data,
    )


def _pelias_search_feature_to_result(text: str, feature: dict[str, Any]) -> Optional[GeocodingResult]:
    """Map one Pelias /v1/search GeoJSON feature to a ``GeocodingResult``."""
    return _pelias_feature_to_result(
        geocoder_name="pelias_search",
        input_str=text,
        feature=feature,
    )


async def geocode_search(
    text: str,
    api_key: Optional[str] = None,
    size: int = 5,
    **kwargs
) -> Optional[GeocodingResult]:
    """
    Geocode a location using Pelias search endpoint.
    
    Args:
        text: Location text to geocode
        api_key: Pelias/Geocode.Earth API key (optional)
        size: Maximum number of results to return
        **kwargs: Additional parameters to pass to Pelias (e.g., boundary.country, focus.point.lat)
        
    Returns:
        GeocodingResult if successful, None otherwise
    """
    try:
        url = "https://api.geocode.earth/v1/search"
        params = {
            "text": text,
            "size": size,
            **kwargs
        }
        
        if api_key:
            params["api_key"] = api_key
        
        logger.info(f"Pelias search geocoding: {text}")
        
        async with httpx.AsyncClient(timeout=_PELIAS_HTTP_TIMEOUT) as client:
            response = await _pelias_get(client, url, params)
            response.raise_for_status()
            data = response.json()
        
        features = data.get("features", [])
        if not features:
            logger.warning(f"No results found for: {text}")
            return None

        return _pelias_search_feature_to_result(text, features[0])

    except Exception as e:
        _log_pelias_exception("search geocoding", e, detail=f"text={text!r}")
        return None


async def geocode_search_candidates(
    text: str,
    api_key: Optional[str] = None,
    size: int = 5,
    **kwargs: Any,
) -> list[GeocodingResult]:
    """
    Same Pelias /v1/search request as ``geocode_search`` but return one result per feature.

    Skips features that cannot be mapped to a ``GeocodingResult`` (e.g. unexpected geometry).
    """
    out: list[GeocodingResult] = []
    try:
        url = "https://api.geocode.earth/v1/search"
        params: dict[str, Any] = {
            "text": text,
            "size": size,
            **kwargs,
        }

        if api_key:
            params["api_key"] = api_key

        logger.info("Pelias search candidates: %s", text)

        async with httpx.AsyncClient(timeout=_PELIAS_HTTP_TIMEOUT) as client:
            response = await _pelias_get(client, url, params)
            response.raise_for_status()
            data = response.json()

        for feature in data.get("features", []):
            if not isinstance(feature, dict):
                continue
            mapped = _pelias_search_feature_to_result(text, feature)
            if mapped is not None:
                out.append(mapped)
        if not out:
            logger.warning("No mappable Pelias search candidates for: %s", text)
        return out
    except Exception as e:
        _log_pelias_exception("search candidates", e, detail=f"text={text!r}")
        return []


async def geocode_structured(
    address: Optional[str] = None,
    locality: Optional[str] = None,
    county: Optional[str] = None,
    region: Optional[str] = None,
    neighbourhood: Optional[str] = None,
    postalcode: Optional[str] = None,
    country: str = "US",
    api_key: Optional[str] = None,
    **kwargs
) -> Optional[GeocodingResult]:
    """
    Geocode using Pelias structured endpoint with address components.
    
    Args:
        address: Street address (e.g., "100 Main St")
        locality: City/town name
        county: County name
        region: State/province name
        neighbourhood: Neighborhood name
        postalcode: ZIP/postal code
        country: Country code (default: "US")
        api_key: Pelias/Geocode.Earth API key (optional)
        **kwargs: Additional parameters to pass to Pelias
        
    Returns:
        GeocodingResult if successful, None otherwise
    """
    try:
        url = "https://api.geocode.earth/v1/search/structured"
        
        params = {"country": country}
        
        # Add provided components
        if address:
            params["address"] = address
        if locality:
            params["locality"] = locality
        if county:
            params["county"] = county
        if neighbourhood:
            params["neighbourhood"] = neighbourhood
        if region:
            params["region"] = region
        if postalcode:
            params["postalcode"] = postalcode
        
        # Add any additional params
        params.update(kwargs)
        
        if api_key:
            params["api_key"] = api_key
        
        logger.info("Pelias structured geocoding: %s", _params_for_log(params))

        async with httpx.AsyncClient(timeout=_PELIAS_HTTP_TIMEOUT) as client:
            response = await _pelias_get(client, url, params)
            response.raise_for_status()
            data = response.json()
        
        features = data.get("features", [])
        if not features:
            logger.warning(f"No results found for structured query")
            return None
        
        # Build input string from components
        input_parts = [p for p in [address, locality, county, region, postalcode, country] if p]
        input_str = ", ".join(input_parts)

        mapped = _pelias_feature_to_result(
            geocoder_name="pelias_structured",
            input_str=input_str,
            feature=features[0],
        )
        if mapped is None:
            logger.warning("No mappable Pelias structured result for input=%s", input_str)
        return mapped

    except Exception as e:
        raw_params = locals().get("params")
        if isinstance(raw_params, dict):
            safe = {k: v for k, v in raw_params.items() if k != "api_key"}
            detail = f"params={safe!r}"
        else:
            detail = "params=<unavailable>"
        _log_pelias_exception("structured geocoding", e, detail=detail)
        return None


async def geocode_structured_candidates(
    *,
    address: Optional[str] = None,
    locality: Optional[str] = None,
    county: Optional[str] = None,
    region: Optional[str] = None,
    neighbourhood: Optional[str] = None,
    postalcode: Optional[str] = None,
    country: str = "US",
    api_key: Optional[str] = None,
    size: int = 5,
    **kwargs: Any,
) -> list[GeocodingResult]:
    """Structured Pelias request returning one ``GeocodingResult`` per feature."""
    out: list[GeocodingResult] = []
    try:
        url = "https://api.geocode.earth/v1/search/structured"

        params: dict[str, Any] = {"country": country, "size": size}
        if address:
            params["address"] = address
        if locality:
            params["locality"] = locality
        if county:
            params["county"] = county
        if neighbourhood:
            params["neighbourhood"] = neighbourhood
        if region:
            params["region"] = region
        if postalcode:
            params["postalcode"] = postalcode
        params.update(kwargs)

        if api_key:
            params["api_key"] = api_key

        input_parts = [p for p in [address, locality, county, region, postalcode, country] if p]
        input_str = ", ".join(input_parts)

        logger.info("Pelias structured candidates: %s", _params_for_log(params))

        async with httpx.AsyncClient(timeout=_PELIAS_HTTP_TIMEOUT) as client:
            response = await _pelias_get(client, url, params)
            response.raise_for_status()
            data = response.json()

        for feature in data.get("features", []):
            if not isinstance(feature, dict):
                continue
            mapped = _pelias_feature_to_result(
                geocoder_name="pelias_structured",
                input_str=input_str,
                feature=feature,
            )
            if mapped is not None:
                out.append(mapped)

        if not out:
            logger.warning("No mappable Pelias structured candidates for input=%s", input_str)
        return out
    except Exception as e:
        safe = {k: v for k, v in params.items() if k != "api_key"} if "params" in locals() else {}
        _log_pelias_exception("structured candidates", e, detail=f"params={safe!r}")
        return []


async def reverse_geocode(
    lat: float,
    lon: float,
    api_key: Optional[str] = None,
    **kwargs
) -> Optional[GeocodingResult]:
    """
    Reverse geocode coordinates using Pelias.
    
    Args:
        lat: Latitude
        lon: Longitude
        api_key: Pelias/Geocode.Earth API key (optional)
        **kwargs: Additional parameters to pass to Pelias
        
    Returns:
        GeocodingResult if successful, None otherwise
    """
    try:
        url = "https://api.geocode.earth/v1/reverse"
        params = {
            "point.lat": lat,
            "point.lon": lon,
            "size": 1,
            **kwargs
        }
        
        if api_key:
            params["api_key"] = api_key
        
        logger.info(f"Pelias reverse geocoding: ({lat}, {lon})")
        
        async with httpx.AsyncClient(timeout=_PELIAS_HTTP_TIMEOUT) as client:
            response = await _pelias_get(client, url, params)
            response.raise_for_status()
            data = response.json()
        
        features = data.get("features", [])
        if not features:
            logger.warning(f"No results found for coordinates: ({lat}, {lon})")
            return None
        
        feature = features[0]
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        rev_layer = str(properties.get("layer", "") or "")
        
        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            logger.warning("Invalid coordinates in result")
            return None
        
        result_lon, result_lat = coords[0], coords[1]
        
        # Build result
        input_str = f"{lat}, {lon}"
        result_data = GeocodingResultData(
            id=properties.get("gid"),  # Use gid (Who's On First ID) instead of id
            processed_str=properties.get("label", input_str),
            geometry=GeometryPoint(
                type="Point",
                coordinates=[result_lon, result_lat]
            ),
            confidence={"pelias_layer": rev_layer},
        )
        
        return GeocodingResult(
            geocoder="pelias_reverse",
            input_str=input_str,
            result=result_data
        )

    except Exception as e:
        _log_pelias_exception("reverse geocoding", e, detail=f"lat={lat!r} lon={lon!r}")
        return None
