"""Location ``type`` strings from PlaceExtract (prompt: ``place_extract/prompts/extract.md``)."""

# Order matches the "Valid types are" section of the PlaceExtract classification prompt.
PLACE_EXTRACT_LOCATION_TYPES: tuple[str, ...] = (
    "place",
    "address",
    "intersection_road",
    "intersection_highway",
    "street_road",
    "span",
    "neighborhood",
    "region_city",
    "city",
    "county",
    "region_state",
    "state",
    "region_national",
    "country",
    "natural",
    "other",
)
