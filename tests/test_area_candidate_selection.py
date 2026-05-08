"""Area-model candidate selection prefers Pelias WOF bbox results."""

from __future__ import annotations

from agate_nodes.geocode_agent.models.area.area import Area
from agate_utils.geocoding.geocoding_types import (
    GeocodingResult,
    GeocodingResultData,
    GeometryPoint,
    GeometryPolygon,
    bbox_west_south_east_north_to_polygon_coordinates,
)


class _DummyCounty(Area):
    def _prep(self) -> dict:
        raise NotImplementedError


def _gr(*, label: str, layer: str, source: str, has_bbox: bool) -> GeocodingResult:
    geom = (
        GeometryPolygon(
            coordinates=bbox_west_south_east_north_to_polygon_coordinates(
                [-88.26, 41.46, -87.11, 42.15]
            )
        )
        if has_bbox
        else GeometryPoint(type="Point", coordinates=[-87.6, 41.9])
    )
    return GeocodingResult(
        geocoder="pelias_structured",
        input_str="q",
        result=GeocodingResultData(
            id=(
                "whosonfirst:county:102084317"
                if source == "whosonfirst"
                else "geonames:county:4888671"
            ),
            processed_str=label,
            geometry=geom,
            confidence={
                "pelias_layer": layer,
                "pelias_source": source,
                "pelias_has_bbox": has_bbox,
                "pelias_match_type": "exact",
            },
        ),
    )


def test_prefers_wof_with_bbox_over_geonames_point() -> None:
    model = _DummyCounty(name="Cook County", country="US")
    geonames = _gr(label="Cook County, IL, USA", layer="county", source="geonames", has_bbox=False)
    wof = _gr(label="Cook County, IL, USA", layer="county", source="whosonfirst", has_bbox=True)

    chosen = model._choose_best_area_candidate([geonames, wof], expected_layer="county")
    assert chosen is not None
    assert chosen.result.confidence["pelias_source"] == "whosonfirst"
    assert chosen.result.geometry.type == "Polygon"


def test_accepts_wof_point_when_no_bbox() -> None:
    model = _DummyCounty(name="Cook County", country="US")
    wof_point = _gr(
        label="Cook County, IL, USA",
        layer="county",
        source="whosonfirst",
        has_bbox=False,
    )
    chosen = model._choose_best_area_candidate([wof_point], expected_layer="county")
    assert chosen is not None
    assert chosen.result.confidence["pelias_source"] == "whosonfirst"
    assert chosen.result.geometry.type == "Point"

