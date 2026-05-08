import logging
from typing import Dict, Any

from .area import Area

logger = logging.getLogger(__name__)

########## STATE MODEL ##########

class State(Area):
    """Model for state-level locations."""

    ########## PRIVATE/HELPER METHODS ##########

    def _prep(self) -> Dict[str, Any]:
        """Prepare state data for geocoding."""
        boundary_country = self.country if isinstance(self.country, str) and self.country.strip() else None
        return {
            "pelias_structured": {
                "region": self.name,
                "country": self.country,
                "size": 5,
                "layers": "region",
                **({"boundary.country": boundary_country} if boundary_country else {}),
            },
            "pelias_search": {
                "text": f"{self.name}, {self.country}",
                "size": 5,
                "layers": "region",
                **({"boundary.country": boundary_country} if boundary_country else {}),
            },
            "geocodio": {
                "query": f"{self.name}, {self.country}",
            },
            "nominatim": {
                "query": f"{self.name}, {self.country}",
            },
        }