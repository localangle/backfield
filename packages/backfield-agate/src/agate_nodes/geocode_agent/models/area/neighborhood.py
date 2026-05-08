import logging
from typing import Dict, Any, Optional
from pydantic import Field

from .area import Area

logger = logging.getLogger(__name__)

########## NEIGHBORHOOD MODEL ##########

class Neighborhood(Area):
    """Model for neighborhood-level locations."""

    city: str = Field(description="Full city name")
    state: str = Field(description="Full state name")
    county: str = Field(default="", description="County name if known")

    ########## PRIVATE/HELPER METHODS ##########

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
        boundary_country = self.country if isinstance(self.country, str) and self.country.strip() else None
        query = f"{self.name}, {self.city}, {self.state}, {self.country}"
        return {
            "pelias_structured": {
                "neighbourhood": self.name,
                "locality": self.city,
                "region": self.state,
                "country": self.country,
                "size": 5,
                "layers": "neighbourhood",
                **({"boundary.country": boundary_country} if boundary_country else {}),
            },
            "pelias_search": {
                "text": query,
                "size": 5,
                "layers": "neighbourhood",
                **({"boundary.country": boundary_country} if boundary_country else {}),
            },
            "geocodio": {"query": query},
            "nominatim": {"query": query},
        }
