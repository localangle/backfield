import logging
from typing import Dict, Any

from pydantic import Field

from .area import Area

logger = logging.getLogger(__name__)

########## COUNTY MODEL ##########

class County(Area):
    """Model for county-level locations."""

    state: str = Field(description="Full state name")

    def _prep(self) -> Dict[str, Any]:
        """Prepare county data for geocoding."""
        boundary_country = self.country if isinstance(self.country, str) and self.country.strip() else None
        return {
            "pelias_structured": {
                "county": self.name,
                "region": self.state,
                "country": self.country,
                "size": 5,
                "layers": "county",
                **({"boundary.country": boundary_country} if boundary_country else {}),
            },
            "pelias_search": {
                "text": f"{self.name}, {self.state}, {self.country}",
                "size": 5,
                "layers": "county",
                **({"boundary.country": boundary_country} if boundary_country else {}),
            },
            "geocodio": {
                "query": f"{self.name}, {self.state}, {self.country}",
            },
            "nominatim": {
                "query": f"{self.name}, {self.state}, {self.country}",
            },
        }
