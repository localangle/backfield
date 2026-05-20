/**
 * Mirror of ``backfield_stylebook.place_extract_location_types.PLACE_EXTRACT_LOCATION_TYPES``.
 * Keep in sync with ``apps/stylebook-ui/src/lib/place-extract-type-label.ts``.
 */
export const PLACE_EXTRACT_LOCATION_TYPES = [
  'place',
  'address',
  'intersection_road',
  'intersection_highway',
  'street_road',
  'span',
  'political_district',
  'neighborhood',
  'region_city',
  'city',
  'county',
  'region_state',
  'state',
  'region_national',
  'country',
  'natural',
  'other',
] as const

/** Explicit labels for PlaceExtract ``location.type`` values used in review UI. */
const TYPE_LABEL_OVERRIDES: Record<string, string> = {
  region_city: 'Region (City)',
  region_national: 'Region (National)',
  region_state: 'Region (State)',
  intersection_road: 'Intersection (Road)',
  intersection_highway: 'Intersection (Highway)',
  street_road: 'Street/Road',
  political_district: 'Political district',
}

/** Human label for a PlaceExtract ``location.type`` value (snake_case → title case, with overrides). */
/** Sort type slugs A–Z by display label; ``other`` last. */
export function sortPlaceExtractTypeOptions(types: readonly string[]): string[] {
  const list = types.filter((t) => String(t).trim() !== '')
  const other: string[] = []
  const rest: string[] = []
  for (const t of list) {
    if (t.toLowerCase() === 'other') other.push(t)
    else rest.push(t)
  }
  rest.sort((a, b) =>
    placeExtractTypeLabel(a).localeCompare(placeExtractTypeLabel(b), undefined, {
      sensitivity: 'base',
    }),
  )
  return [...rest, ...other]
}

export function placeExtractTypeLabel(value: string): string {
  const raw = value.trim()
  if (!raw) return value
  const key = raw.toLowerCase()
  const mapped = TYPE_LABEL_OVERRIDES[key]
  if (mapped) return mapped
  return raw
    .split('_')
    .map((part) => (part ? part.charAt(0).toUpperCase() + part.slice(1).toLowerCase() : ''))
    .filter(Boolean)
    .join(' ')
}
