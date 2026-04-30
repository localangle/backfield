from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from agate_utils.geocoding.geocoding_types import GeocodingResult

class Location(BaseModel):
    """
    Base model for all location types.
    """
    name: str = Field(description="The name of the location")
    city: Optional[str] = Field(default=None, description="City name if applicable")
    state_abbr: Optional[str] = Field(default=None, description="State abbreviation if applicable")
    country: str = Field(default="US", description="Country code")
    geocoding_result: Optional[GeocodingResult] = Field(default=None, description="Stored geocoding result")
    
    def _prep(self) -> Dict[str, Any]:
        """Prepare location data for geocoding."""
        raise NotImplementedError("This method is not implemented for this place type")
    
    def _get_best_candidate(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Select the best geocoding candidate from multiple results."""
        raise NotImplementedError("This method is not implemented for this place type")

    async def geocode(self) -> Optional[GeocodingResult]:
        """Geocode this location using appropriate services."""
        raise NotImplementedError("This method is not implemented for this place type")
