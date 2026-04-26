/**
 * Mirror of ``backfield_stylebook.place_extract_location_types.PLACE_EXTRACT_LOCATION_TYPES``.
 * Keep in sync when the PlaceExtract taxonomy changes.
 */
export const PLACE_EXTRACT_LOCATION_TYPES = [
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
] as const

/** Explicit labels for PlaceExtract ``location.type`` values used in the review queue UI. */
const TYPE_LABEL_OVERRIDES: Record<string, string> = {
  region_city: "Region (City)",
  region_national: "Region (National)",
  region_state: "Region (State)",
  intersection_road: "Intersection (Road)",
  intersection_highway: "Intersection (Highway)",
  street_road: "Street/Road",
}

/** Human label for a PlaceExtract `location.type` value (snake_case → Title Case words, with overrides). */
export function placeExtractTypeLabel(value: string): string {
  const raw = value.trim()
  if (!raw) return value
  const key = raw.toLowerCase()
  const mapped = TYPE_LABEL_OVERRIDES[key]
  if (mapped) return mapped
  return raw
    .split("_")
    .map((part) => (part ? part.charAt(0).toUpperCase() + part.slice(1).toLowerCase() : ""))
    .filter(Boolean)
    .join(" ")
}

/**
 * Sort type filter values A–Z by display label; ``other`` (any casing) stays last.
 */
export function sortReviewQueueTypeFilterOptions(types: string[]): string[] {
  const list = types.filter((t) => String(t).trim() !== "")
  const other: string[] = []
  const rest: string[] = []
  for (const t of list) {
    if (t.toLowerCase() === "other") other.push(t)
    else rest.push(t)
  }
  rest.sort((a, b) =>
    placeExtractTypeLabel(a).localeCompare(placeExtractTypeLabel(b), undefined, {
      sensitivity: "base",
    }),
  )
  return [...rest, ...other]
}
