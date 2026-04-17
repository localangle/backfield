import logging
from typing import Dict, Any

from pydantic import Field

from .area import Area

logger = logging.getLogger(__name__)

########## COUNTY MODEL ##########

class County(Area):
    """Model for county-level locations."""

    state: str = Field(description="Full state name")

    ########## PRIVATE/HELPER METHODS ##########

    def _prep(self) -> Dict[str, Any]:
        """Prepare county data for geocoding."""
        return {
            "pelias_structured": {
                "county": self.name,
                "region": self.state,
                "country": self.country,
                "size": 1,
            },
            "pelias_search": {
                "text": f"{self.name}, {self.state}, {self.country}",
            },
            "geocodio": {
                "query": f"{self.name}, {self.state}, {self.country}",
            },
            "nominatim": {
                "query": f"{self.name}, {self.state}, {self.country}",
            },
        }
