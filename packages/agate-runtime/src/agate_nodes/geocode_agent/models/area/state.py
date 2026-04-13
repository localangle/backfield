import logging
from typing import Dict, Any, List

from .area import Area

logger = logging.getLogger(__name__)

########## STATE MODEL ##########

class State(Area):
    """Model for state-level locations."""

    ########## PRIVATE/HELPER METHODS ##########

    def _prep(self) -> Dict[str, Any]:
        """Prepare state data for geocoding."""
        return {
            "pelias_structured": {
                "region": self.name,
                "country": self.country,
                "size": 1,
            },
            "pelias_search": {
                "text": f"{self.name}, {self.country}",
            },
            "geocodio": {
                "query": f"{self.name}, {self.country}",
            },
            "nominatim": {
                "query": f"{self.name}, {self.country}",
            },
        }

    ########## PUBLIC METHODS ##########

    def get_parents(self) -> List[Dict[str, str]]:
        """States currently have no parents beyond the country."""
        return []