"""Pydantic schemas for PlaceExtract location objects (no runtime imports)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StateInfo(BaseModel):
    """State information."""

    name: str = Field(description="Full name of the state")
    abbr: str = Field(description="Postal abbreviation for the state")


class CountryInfo(BaseModel):
    """Country information."""

    name: str = Field(description="Full name of the country")
    abbr: str = Field(description="ISO 3166-1 country code")


class StreetRoadInfo(BaseModel):
    """Street/Road information for street_road types."""

    name: str = Field(description="Name of the street")
    boundary: str = Field(description="Geocodable boundary string for the street")


class PlaceInfo(BaseModel):
    """Place information for named places."""

    name: str = Field(description="Name of the place")
    addressable: bool = Field(
        default=False, description="Whether the place has a findable street address"
    )
    natural: bool = Field(
        default=False, description="Whether the place represents a natural location"
    )


class SpanEndpoint(BaseModel):
    """Endpoint for a span of road."""

    type: str = Field(description="The kind of endpoint (city or intersection)")
    location: str = Field(description="Geocodable representation of the endpoint")


class SpanInfo(BaseModel):
    """Span information for span types."""

    start: Optional[SpanEndpoint] = Field(default=None, description="Span starting point")
    end: Optional[SpanEndpoint] = Field(default=None, description="Span ending point")


class LocationComponents(BaseModel):
    """Components of a location."""

    place: Optional[PlaceInfo] = Field(default=None, description="Place information if applicable")
    street_road: Optional[StreetRoadInfo] = Field(
        default=None, description="Street/road information if applicable"
    )
    span: Optional[SpanInfo] = Field(default=None, description="Span information for span types")
    address: Optional[str] = Field(default="", description="Street address if applicable")
    neighborhood: Optional[str] = Field(default="", description="Neighborhood name if applicable")
    city: Optional[str] = Field(default="", description="City name if applicable")
    county: Optional[str] = Field(default="", description="County name if applicable")
    state: Optional[StateInfo] = Field(default=None, description="State information if applicable")
    country: Optional[CountryInfo] = Field(default=None, description="Country information if applicable")


class LocationInfo(BaseModel):
    """Location information."""

    full: str = Field(description="The full geocodable location string")
    type: str = Field(description="The type of location (e.g., city, address, intersection_road)")
    components: LocationComponents = Field(description="Detailed components of the location")


class PlaceMention(BaseModel):
    """One verbatim story mention of a location."""

    text: str = Field(description="Verbatim text from the story for this mention")


class Place(BaseModel):
    """A place extracted from text."""

    original_text: str = Field(description="The original text from which this location was extracted")
    mentions: List[PlaceMention] = Field(
        default_factory=list,
        description="Every verbatim story mention of this same real-world place",
    )
    description: str = Field(description="Brief description of the location and its relevance")
    geocode_hints: str = Field(
        default="",
        description="Concise story context for downstream geocoding (disambiguation, vague areas, ties to other mentions)",
    )
    location: LocationInfo = Field(description="Location information with components")
    model_config = ConfigDict(extra="allow")  # Allow additional fields like 'mural'
