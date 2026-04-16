import logging
from typing import Dict, Any, List, Optional
from pydantic import Field

from agate_utils.geocoding.geocoding_types import (
    GeometryPolygon,
    bbox_west_south_east_north_to_polygon_coordinates,
)
from agate_utils.geocoding.wof import get_bbox_by_id

from .area import Area

logger = logging.getLogger(__name__)

########## NEIGHBORHOOD MODEL ##########

class Neighborhood(Area):
    """Model for neighborhood-level locations."""

    city: str = Field(description="Full city name")
    state: str = Field(description="Full state name")
    county: str = Field(default="", description="County name if known")

    ########## PRIVATE/HELPER METHODS ##########

    def _lookup_wof_bbox(self, gid: Optional[str]) -> Optional[List[float]]:
        if not gid or "whosonfirst" not in gid:
            return None

        wof_id = gid.split(":")[-1]
        try:
            bbox = get_bbox_by_id(wof_id)
        except FileNotFoundError:
            logger.debug("Who's On First database not available; cannot enrich bbox for %s", self.name)
            return None
        except Exception as exc:
            logger.warning("Error retrieving WOF bbox for %s (%s): %s", self.name, gid, exc)
            return None

        if not bbox or len(bbox) != 4:
            return None

        west, south, east, north = bbox
        if self._is_degenerate_bbox([west, south, east, north]):
            return None

        return [west, south, east, north]

    @staticmethod
    def _is_degenerate_bbox(coords: Optional[Any]) -> bool:
        """True when extent is a line or point (flat bbox or flat polygon ring)."""
        if not coords:
            return True
        if isinstance(coords, list) and len(coords) == 4 and all(
            isinstance(x, (int, float)) for x in coords
        ):
            west, south, east, north = (float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3]))
            return abs(east - west) < 1e-5 or abs(north - south) < 1e-5
        if isinstance(coords, list) and coords and isinstance(coords[0], list):
            ring = coords[0]
            xs: list[float] = []
            ys: list[float] = []
            for pt in ring:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    xs.append(float(pt[0]))
                    ys.append(float(pt[1]))
            if len(xs) < 2:
                return True
            return (max(xs) - min(xs)) < 1e-5 or (max(ys) - min(ys)) < 1e-5
        return True

    def _prep(self) -> Dict[str, Any]:
        """Prepare neighborhood data for geocoding."""
        query = f"{self.name}, {self.city}, {self.state}, {self.country}"
        return {
            "pelias_structured": {
                "neighbourhood": self.name,
                "locality": self.city,
                "region": self.state,
                "country": self.country,
                "size": 1,
            },
            "pelias_search": {"text": query},
            "geocodio": {"query": query},
            "nominatim": {"query": query},
        }

    ########## PUBLIC METHODS ##########

    async def geocode(
        self,
        pelias_api_key: Optional[str] = None,
        geocodio_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        **kwargs: Dict[str, Any],
    ):
        result = await super().geocode(
            pelias_api_key=pelias_api_key,
            geocodio_api_key=geocodio_api_key,
            openai_api_key=openai_api_key,
            **kwargs,
        )

        if not result or not result.result:
            return result

        geometry = result.result.geometry
        if geometry.type == "Polygon" and not self._is_degenerate_bbox(geometry.coordinates):
            self.geocoding_result = result
            return result

        wof_bbox = self._lookup_wof_bbox(result.result.id)
        if wof_bbox:
            try:
                result.result.geometry = GeometryPolygon(
                    coordinates=bbox_west_south_east_north_to_polygon_coordinates(wof_bbox),
                )
            except Exception as exc:
                logger.debug("Failed to apply WOF bbox for neighborhood %s: %s", self.name, exc)

        self.geocoding_result = result
        return result

    def get_parents(self) -> List[Dict[str, str]]:
        """Return city, county, and state parent IDs when available."""
        if not self.geocoding_result or not self.geocoding_result.result:
            return []

        hierarchy = self.geocoding_result.result.parent_hierarchy or {}
        parents: List[Dict[str, str]] = []

        for key in ("state", "county", "city"):
            node = hierarchy.get(key)
            if node and node.get("name") and node.get("id"):
                parents.append({"name": node["name"], "id": node["id"]})

        return parents
