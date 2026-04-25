"""Location ``type`` strings from PlaceExtract (prompt: ``place_extract/prompts/extract.md``).

``private_residence`` is the legacy JSON value for ``address_place_kind`` meaning “not a
publicly patron-accessible venue” (homes, incident intersections, PO boxes, etc.—see prompt).
"""

# Values for ``address_place_kind`` (PlaceExtract output); also used by canonical deferral.
ADDRESS_PLACE_KIND_PUBLIC_NAMED = "public_named"
ADDRESS_PLACE_KIND_PRIVATE_RESIDENCE = "private_residence"
ADDRESS_PLACE_KIND_UNKNOWN = "unknown"

# Street-level types for ``address_place_kind`` (model may emit ``address_intersection`` too).
ADDRESS_LIKE_LOCATION_TYPES: frozenset[str] = frozenset(
    {
        "address",
        "address_intersection",
        "intersection_road",
        "intersection_highway",
        "street_road",
        "span",
    }
)


def is_address_like_location_type(location_type: str | None) -> bool:
    """True when ``location_type`` participates in ``address_place_kind`` classification (v1)."""
    lt = (location_type or "").strip().lower()
    return lt in ADDRESS_LIKE_LOCATION_TYPES


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
