import logging
from typing import Dict, Any, List

from pydantic import Field

from .area import Area

logger = logging.getLogger(__name__)

########## CITY MODEL ##########

class City(Area):
    """Model for city-level locations."""

    state: str = Field(description="Full state name")
    county: str = Field(default="", description="County name if known")

    ########## PRIVATE/HELPER METHODS ##########

    def _prep(self) -> Dict[str, Any]:
        """Prepare city data for geocoding."""
        return {
            "pelias_structured": {
                "locality": self.name,
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

    ########## PUBLIC METHODS ##########

    def get_parents(self) -> List[Dict[str, str]]:
        """Return state and county parent IDs when available."""
        if not self.geocoding_result or not self.geocoding_result.result or not self.geocoding_result.result.parent_hierarchy:
            return []

        parent_hierarchy = self.geocoding_result.result.parent_hierarchy
        parent_ids: List[Dict[str, str]] = []

        # Add state
        if parent_hierarchy.get("state"):
            state = parent_hierarchy["state"]
            if state.get("name") and state.get("id"):
                parent_ids.append({
                    "name": state["name"],
                    "id": state["id"],
                })

        # Add county
        if parent_hierarchy.get("county"):
            county = parent_hierarchy["county"]
            if county.get("name") and county.get("id"):
                parent_ids.append({
                    "name": county["name"],
                    "id": county["id"],
                })

        return parent_ids
