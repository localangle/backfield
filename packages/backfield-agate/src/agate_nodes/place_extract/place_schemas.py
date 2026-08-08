"""Pydantic schemas for PlaceExtract location objects (no runtime imports)."""

from __future__ import annotations

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
        default=True,
        description=(
            "Whether the place should attempt POI geocoding. Named destinations "
            "(venues, parks, zoos, plazas) are addressable even without a mailing line."
        ),
    )
    natural: bool = Field(
        default=False,
        description=(
            "Whether the place is a true geographic feature. Prefer type=natural instead; "
            "do not set from name tokens like park or river."
        ),
    )


class SpanEndpoint(BaseModel):
    """Endpoint for a span of road."""

    type: str = Field(description="The kind of endpoint (city or intersection)")
    location: str = Field(description="Geocodable representation of the endpoint")


class SpanInfo(BaseModel):
    """Span information for span types."""

    start: SpanEndpoint | None = Field(default=None, description="Span starting point")
    end: SpanEndpoint | None = Field(default=None, description="Span ending point")


class LocationComponents(BaseModel):
    """Components of a location."""

    place: PlaceInfo | None = Field(default=None, description="Place information if applicable")
    street_road: StreetRoadInfo | None = Field(
        default=None, description="Street/road information if applicable"
    )
    span: SpanInfo | None = Field(default=None, description="Span information for span types")
    address: str | None = Field(default="", description="Street address if applicable")
    neighborhood: str | None = Field(default="", description="Neighborhood name if applicable")
    city: str | None = Field(default="", description="City name if applicable")
    county: str | None = Field(default="", description="County name if applicable")
    postal_code: str | None = Field(default="", description="Postal code if applicable")
    state: StateInfo | None = Field(default=None, description="State information if applicable")
    country: CountryInfo | None = Field(default=None, description="Country information if applicable")


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
    mentions: list[PlaceMention] = Field(
        default_factory=list,
        description="Every verbatim story mention of this same real-world place",
    )
    description: str = Field(description="Brief description of the location and its relevance")
    geocode_hints: str = Field(
        default="",
        description=(
            "Geographic disambiguation for downstream geocoding/search: street, neighborhood, "
            "nearby landmark, or which branch—not story synopsis"
        ),
    )
    location: LocationInfo = Field(description="Location information with components")
    model_config = ConfigDict(extra="allow")  # Allow additional fields like 'mural'
