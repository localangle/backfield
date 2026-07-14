/**
 * Processed-item verification: place geometry helpers with LeafletMap parity.
 * See ``docs/api/processed-item-review.md`` → *Entity review domains*.
 */

import {
  isLocationLinkedToStylebookCanonical,
  normalizeOverlay,
} from '../../overlay/verificationOverlay'

export type GeoJsonGeometry =
  | { type: 'Point'; coordinates: [number, number] }
  | { type: 'Polygon'; coordinates: [number, number][][] }
  | { type: 'MultiPolygon'; coordinates: [number, number][][][] }

export function isPointGeometry(geometry: Record<string, unknown> | null): geometry is {
  type: 'Point'
  coordinates: [number, number]
} {
  if (!geometry || typeof geometry !== 'object') return false
  const g = geometry as Record<string, unknown>
  if (g.type !== 'Point') return false
  const c = g.coordinates
  return Array.isArray(c) && c.length === 2 && typeof c[0] === 'number' && typeof c[1] === 'number'
}

export function isPolygonGeometry(geometry: Record<string, unknown> | null): geometry is {
  type: 'Polygon'
  coordinates: number[][][]
} {
  if (!geometry || typeof geometry !== 'object') return false
  const g = geometry as Record<string, unknown>
  if (g.type !== 'Polygon') return false
  const c = g.coordinates
  return Array.isArray(c) && c.length > 0
}

const MAX_POSITIONS = 4000

function countPositions(coords: unknown, depth: number): number {
  if (depth > 6) return MAX_POSITIONS + 1
  if (typeof coords === 'number') {
    return Number.isFinite(coords) ? 1 : MAX_POSITIONS + 1
  }
  if (!Array.isArray(coords)) return MAX_POSITIONS + 1
  let n = 0
  for (const x of coords) {
    n += countPositions(x, depth + 1)
  }
  return n
}

function validateLngLat(lng: number, lat: number): boolean {
  return (
    Number.isFinite(lng) &&
    Number.isFinite(lat) &&
    lng >= -180 &&
    lng <= 180 &&
    lat >= -90 &&
    lat <= 90
  )
}

/** Client-side guard aligned with ``api.processed_item.overlay.validate`` (subset). */
export function validateGeometryObject(geometry: Record<string, unknown> | null): string | null {
  if (!geometry || typeof geometry !== 'object') return 'Geometry is missing.'
  const t = geometry.type
  if (t !== 'Point' && t !== 'Polygon' && t !== 'MultiPolygon') {
    return 'Geometry must be a point, an area, or a multi-area shape.'
  }
  const coords = geometry.coordinates
  if (countPositions(coords, 0) > MAX_POSITIONS) {
    return 'That shape has too many coordinates to save.'
  }
  if (t === 'Point') {
    if (!Array.isArray(coords) || coords.length !== 2) {
      return 'A point must be a single map position.'
    }
    const lng = Number(coords[0])
    const lat = Number(coords[1])
    if (!validateLngLat(lng, lat)) return 'That point is outside the valid map range.'
    return null
  }
  if (t === 'Polygon') {
    if (!Array.isArray(coords) || coords.length < 1) return 'An area must include at least one outline ring.'
    const outer = coords[0]
    if (!Array.isArray(outer) || outer.length < 4) {
      return 'An area outline must include at least three corners.'
    }
    for (const pt of outer) {
      if (!Array.isArray(pt) || pt.length < 2) return 'Each corner must be a map position.'
      if (!validateLngLat(Number(pt[0]), Number(pt[1]))) return 'That area is outside the valid map range.'
    }
    return null
  }
  if (!Array.isArray(coords) || coords.length < 1) return 'A multi-area shape must list at least one area.'
  return null
}

/** Keep in sync with ``api.processed_item.entities.location.locations_merge`` anchor helper (Python). */
function anchorForPlaceDict(place: Record<string, unknown>, nodeId: string, index: number): string {
  for (const key of ['id', 'mention_id'] as const) {
    const raw = place[key]
    if (raw === undefined || raw === null) continue
    const s = String(raw).trim()
    if (!s || s.startsWith('h3:')) continue
    return s
  }
  return `${nodeId}:${index}`
}

/** Keep in sync with ``api.processed_item.entities.location.locations_merge`` (Python). */
const GEOCODED_PLACES_NODE_PRIORITY = [
  'stylebook_output',
  'stylebook-output',
  'DBOutput',
  'db_output',
  'GeocodeAgent',
  'geocode_agent',
  'Geocode',
] as const

const PLACE_EXTRACT_NODE_IDS = new Set(['place_extract', 'PlaceExtract'])

function nodeIdsWithPlaces(output: Record<string, unknown>): Set<string> {
  const ids = new Set<string>()
  for (const [nodeId, payload] of Object.entries(output)) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) continue
    if (typeof (payload as Record<string, unknown>).places === 'object' && (payload as Record<string, unknown>).places !== null) {
      ids.add(nodeId)
    }
  }
  return ids
}

function geocodedPlacesNodeCandidates(output: Record<string, unknown>): Set<string> {
  const excludedLower = new Set([...PLACE_EXTRACT_NODE_IDS].map((n) => n.toLowerCase()))
  return new Set(
    [...nodeIdsWithPlaces(output)].filter(
      (n) => !PLACE_EXTRACT_NODE_IDS.has(n) && !excludedLower.has(n.toLowerCase()),
    ),
  )
}

function selectGeocodedPlacesNodeId(output: Record<string, unknown>): string | null {
  const placesNodes = geocodedPlacesNodeCandidates(output)
  if (placesNodes.size === 0) return null
  const nodeSet = new Set(placesNodes)
  for (const pref of GEOCODED_PLACES_NODE_PRIORITY) {
    if (nodeSet.has(pref)) return pref
  }
  const lowerMap = new Map<string, string>()
  for (const n of nodeSet) lowerMap.set(n.toLowerCase(), n)
  for (const pref of GEOCODED_PLACES_NODE_PRIORITY) {
    const hit = lowerMap.get(pref.toLowerCase())
    if (hit) return hit
  }
  return [...nodeSet].sort()[0] ?? null
}

function iterRowsFromPlacesNode(
  output: Record<string, unknown>,
  nodeId: string,
): Array<{ anchor: string; nodeId: string; index: number; location: Record<string, unknown> }> {
  const rows: Array<{ anchor: string; nodeId: string; index: number; location: Record<string, unknown> }> = []
  const payload = output[nodeId]
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return rows
  const places = (payload as Record<string, unknown>).places
  if (!places || typeof places !== 'object' || Array.isArray(places)) return rows
  const pl = places as Record<string, unknown>
  let idx = 0
  const areas = pl.areas
  if (areas && typeof areas === 'object' && !Array.isArray(areas)) {
    const ar = areas as Record<string, unknown>
    for (const bucket of ['states', 'counties', 'cities', 'neighborhoods', 'regions', 'other'] as const) {
      const items = ar[bucket]
      if (!Array.isArray(items)) continue
      for (const loc of items) {
        if (!loc || typeof loc !== 'object' || Array.isArray(loc)) continue
        const place = loc as Record<string, unknown>
        rows.push({ anchor: anchorForPlaceDict(place, nodeId, idx), nodeId, index: idx, location: place })
        idx += 1
      }
    }
  }
  for (const bucket of ['points', 'needs_review', 'other'] as const) {
    const items = pl[bucket]
    if (!Array.isArray(items)) continue
    for (const loc of items) {
      if (!loc || typeof loc !== 'object' || Array.isArray(loc)) continue
      const place = loc as Record<string, unknown>
      rows.push({ anchor: anchorForPlaceDict(place, nodeId, idx), nodeId, index: idx, location: place })
      idx += 1
    }
  }
  return rows
}

/** Baseline place rows for overlay math: geocoded ``places`` only (never PlaceExtract ``locations``). */
export function iterBaselinePlacesFromOutput(
  output: Record<string, unknown> | null | undefined,
): Array<{ anchor: string; nodeId: string; index: number; location: Record<string, unknown> }> {
  if (!output || typeof output !== 'object') return []
  const geocodedNode = selectGeocodedPlacesNodeId(output)
  if (!geocodedNode) return []
  return iterRowsFromPlacesNode(output, geocodedNode)
}

export type GeocodedPlaceDisplay = {
  name: string
  type: string
  formattedAddress: string
  role: string
}

/** Leaflet ``fitBounds`` corners: ``[[southLat, westLng], [northLat, eastLng]]``. */
export type LeafletFitBounds = [[number, number], [number, number]]

function readGeocodeResult(place: Record<string, unknown>): Record<string, unknown> | null {
  const gc = place.geocode
  if (!gc || typeof gc !== 'object' || Array.isArray(gc)) return null
  const res = (gc as Record<string, unknown>).result
  if (!res || typeof res !== 'object' || Array.isArray(res)) return null
  return res as Record<string, unknown>
}

/** Source pill when the place has no drawable map geography (needs review, cleared, etc.). */
export const NO_GEOGRAPHY_SOURCE_LABEL = 'No geography'

/** Model QA / failure flags cleared when a reviewer assigns geometry on the map. */
export const PLACE_QA_REVIEW_FLAG_KEYS = [
  'geocode_qa_code',
  'geocode_region_mismatch',
  'geocode_city_level_fallback',
  'geocode_admin_level_mismatch',
] as const

/** Known ``geocode.geocode_type`` values from GeocodeAgent consolidate (user-facing labels). */
const GEOCODE_TYPE_USER_LABELS: Record<string, string> = {
  pelias: 'Address search',
  pelias_structured: 'Address search',
  pelias_search: 'Address search',
  pelias_reverse: 'Address search',
  geocodio_search: 'Geocodio',
  geocodio_structured: 'Geocodio',
  geocodio_reverse: 'Geocodio',
  nominatim: 'OpenStreetMap',
  nominatim_natural: 'OpenStreetMap',
  nominatim_llm_raw: 'OpenStreetMap',
  nominatim_raw_combined: 'OpenStreetMap',
  overpass: 'Street intersection',
  stylebook: 'Stylebook',
  cache: 'Saved geocode',
  manual: 'Manual',
  region_llm: 'Estimated area',
  natural_llm_estimate: 'Estimated area',
  span: 'Road segment',
  parent_stub: 'Parent place',
  wof: 'Gazetteer',
}

function humanizeGeocodeTypeToken(raw: string): string {
  const t = raw.trim().toLowerCase()
  if (!t) return ''
  return t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function readGeocodeConfidenceSource(place: Record<string, unknown>): string {
  const res = readGeocodeResult(place)
  if (!res) return ''
  const conf = res.confidence
  if (!conf || typeof conf !== 'object' || Array.isArray(conf)) return ''
  const src = (conf as Record<string, unknown>).source
  return typeof src === 'string' ? src.trim().toLowerCase() : ''
}

/**
 * User-facing geocoding source from stored run output (``geocode.geocode_type`` and optional
 * ``geocode.result.confidence.source`` when present). Does not add server fields.
 */
export function getGeocodingSourceLabel(
  place: Record<string, unknown> | null | undefined,
): string | null {
  if (!place || typeof place !== 'object') return null
  if (!extractGeometryFromPlace(place)) {
    return NO_GEOGRAPHY_SOURCE_LABEL
  }
  const gc = place.geocode
  if (!gc || typeof gc !== 'object' || Array.isArray(gc)) return null
  const rawType = (gc as Record<string, unknown>).geocode_type
  const geocodeType = typeof rawType === 'string' ? rawType.trim().toLowerCase() : ''
  const confidenceSource = readGeocodeConfidenceSource(place)

  if (geocodeType === 'manual') {
    return GEOCODE_TYPE_USER_LABELS.manual
  }
  if (confidenceSource === 'canonical_db') {
    return 'Stylebook'
  }
  if (confidenceSource === 'location_cache' && !geocodeType) {
    return 'Saved geocode'
  }
  if (!geocodeType) {
    return null
  }
  if (geocodeType in GEOCODE_TYPE_USER_LABELS) {
    return GEOCODE_TYPE_USER_LABELS[geocodeType]
  }
  if (geocodeType.startsWith('pelias')) return 'Address search'
  if (geocodeType.startsWith('geocodio')) return 'Geocodio'
  if (geocodeType.startsWith('nominatim')) return 'OpenStreetMap'
  return humanizeGeocodeTypeToken(geocodeType) || null
}

/** True when the place row has geocoder output (geometry or a formatted line). */
export function isGeocodedPlace(place: Record<string, unknown> | null | undefined): boolean {
  if (!place || typeof place !== 'object') return false
  if (extractGeometryFromPlace(place)) return true
  const res = readGeocodeResult(place)
  if (!res) return false
  const fa = res.formatted_address ?? res.processed_str
  return typeof fa === 'string' && fa.trim().length > 0
}

export type PlaceEditorialDetail = {
  roleInStory: string
  nature: string
  natureSecondaryTags: string[]
}

function parseNatureSecondaryTags(place: Record<string, unknown>): string[] {
  let raw = place.nature_secondary_tags
  if (raw === undefined) raw = place.nature_secondary
  if (!Array.isArray(raw)) return []
  const out: string[] = []
  const seen = new Set<string>()
  for (const x of raw) {
    if (typeof x !== 'string') continue
    const t = x.trim().toLowerCase()
    if (!t || seen.has(t)) continue
    seen.add(t)
    out.push(t)
  }
  return out
}

/** Read ``role_in_story`` from a place row, falling back to PlaceExtract ``description``. */
export function readRoleInStoryFromPlace(place: Record<string, unknown>): string {
  const roleRaw = place.role_in_story
  if (typeof roleRaw === 'string' && roleRaw.trim()) {
    return roleRaw.trim()
  }
  const desc = place.description
  if (typeof desc === 'string' && desc.trim()) {
    return desc.trim()
  }
  return ''
}

/** Editorial context for expanded geocoded-place rows (PlaceExtract / mention fields). */
export function getPlaceEditorialDetail(
  place: Record<string, unknown> | null | undefined,
): PlaceEditorialDetail {
  if (!place || typeof place !== 'object') {
    return { roleInStory: '', nature: '', natureSecondaryTags: [] }
  }
  const roleInStory = readRoleInStoryFromPlace(place)
  const nature = typeof place.nature === 'string' ? place.nature.trim().toLowerCase() : ''
  return {
    roleInStory,
    nature,
    natureSecondaryTags: parseNatureSecondaryTags(place),
  }
}

export function placeEditorialDetailHasContent(detail: PlaceEditorialDetail): boolean {
  return (
    detail.roleInStory.length > 0 ||
    detail.nature.length > 0 ||
    detail.natureSecondaryTags.length > 0
  )
}

/** Display fields for the review geocoded-places list (``role`` maps from extractor ``nature``). */
export function getGeocodedPlaceDisplay(place: Record<string, unknown> | null | undefined): GeocodedPlaceDisplay {
  if (!place || typeof place !== 'object') {
    return { name: '', type: '', formattedAddress: '', role: '' }
  }
  const res = readGeocodeResult(place)

  let name = ''
  const loc = place.location
  if (typeof loc === 'string' && loc.trim()) {
    name = loc.trim()
  } else if (loc && typeof loc === 'object' && !Array.isArray(loc)) {
    const full = (loc as Record<string, unknown>).full
    if (typeof full === 'string' && full.trim()) name = full.trim()
  }
  if (!name && typeof place.description === 'string' && place.description.trim()) {
    name = place.description.trim()
  }

  const type = typeof place.type === 'string' ? place.type.trim() : ''
  const formattedAddress =
    (res && typeof res.formatted_address === 'string' ? res.formatted_address.trim() : '') ||
    (res && typeof res.processed_str === 'string' ? res.processed_str.trim() : '')
  const role = typeof place.nature === 'string' ? place.nature.trim() : ''

  return { name, type, formattedAddress, role }
}

/** Bounds for zooming the verification map to a single place geometry. */
export function leafletBoundsFromGeometry(geometry: Record<string, unknown> | null | undefined): LeafletFitBounds | null {
  if (!geometry || typeof geometry !== 'object') return null
  const t = geometry.type
  let minLng = Infinity
  let minLat = Infinity
  let maxLng = -Infinity
  let maxLat = -Infinity
  let has = false

  const bump = (lng: unknown, lat: unknown) => {
    const lo = Number(lng)
    const la = Number(lat)
    if (!Number.isFinite(lo) || !Number.isFinite(la)) return
    minLng = Math.min(minLng, lo)
    minLat = Math.min(minLat, la)
    maxLng = Math.max(maxLng, lo)
    maxLat = Math.max(maxLat, la)
    has = true
  }

  const coords = geometry.coordinates
  if (t === 'Point' && Array.isArray(coords) && coords.length >= 2) {
    bump(coords[0], coords[1])
    if (!has) return null
    const pad = 0.02
    return [
      [minLat - pad, minLng - pad],
      [maxLat + pad, maxLng + pad],
    ]
  }
  if (t === 'Polygon' && Array.isArray(coords)) {
    for (const ring of coords) {
      if (!Array.isArray(ring)) continue
      for (const pt of ring) {
        if (Array.isArray(pt) && pt.length >= 2) bump(pt[0], pt[1])
      }
    }
  } else if (t === 'MultiPolygon' && Array.isArray(coords)) {
    for (const poly of coords) {
      if (!Array.isArray(poly)) continue
      for (const ring of poly) {
        if (!Array.isArray(ring)) continue
        for (const pt of ring) {
          if (Array.isArray(pt) && pt.length >= 2) bump(pt[0], pt[1])
        }
      }
    }
  }
  if (!has || minLng >= maxLng || minLat >= maxLat) return null
  return [
    [minLat, minLng],
    [maxLat, maxLng],
  ]
}

export function extractGeometryFromPlace(place: Record<string, unknown> | null | undefined): Record<
  string,
  unknown
> | null {
  if (!place || typeof place !== 'object') return null
  const top = place.geometry
  if (top && typeof top === 'object' && !Array.isArray(top) && typeof (top as Record<string, unknown>).type === 'string') {
    return top as Record<string, unknown>
  }
  const gc = place.geocode
  if (gc && typeof gc === 'object' && !Array.isArray(gc)) {
    const res = (gc as Record<string, unknown>).result
    if (res && typeof res === 'object' && !Array.isArray(res)) {
      const g = (res as Record<string, unknown>).geometry
      if (g && typeof g === 'object' && !Array.isArray(g) && typeof (g as Record<string, unknown>).type === 'string') {
        return g as Record<string, unknown>
      }
    }
  }
  return null
}

function cloneJson<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}

/** Mark geocode metadata as a manual map edit (review draw, drag, or delete). */
/** Drop model needs-review / QA flags from a shallow ``locations.by_anchor`` patch after geometry assign. */
export function applyOverlayPatchAfterGeometryAssignment(
  patch: Record<string, unknown>,
): Record<string, unknown> {
  const out = { ...patch }
  out.geocoded = true
  for (const key of PLACE_QA_REVIEW_FLAG_KEYS) {
    delete out[key]
  }
  delete out.reason
  return out
}

export function markGeocodeAsManualEdit(geocode: Record<string, unknown>): void {
  geocode.geocode_type = 'manual'
  const prevResult = geocode.result
  const result =
    prevResult && typeof prevResult === 'object' && !Array.isArray(prevResult)
      ? (cloneJson(prevResult) as Record<string, unknown>)
      : ({} as Record<string, unknown>)
  const conf = result.confidence
  if (conf && typeof conf === 'object' && !Array.isArray(conf)) {
    const next = { ...(conf as Record<string, unknown>), source: 'manual' }
    delete next.canonical_id
    result.confidence = next
  } else {
    result.confidence = { source: 'manual' }
  }
  geocode.result = result
}

/**
 * Build a shallow patch fragment with a full ``geocode`` object whose ``result.geometry`` is updated.
 */
export function buildGeocodePatchForGeometry(
  mergedPlaceLocation: Record<string, unknown>,
  geometry: Record<string, unknown>,
): Record<string, unknown> {
  const prevGeocode = mergedPlaceLocation.geocode
  const geocode =
    prevGeocode && typeof prevGeocode === 'object' && !Array.isArray(prevGeocode)
      ? (cloneJson(prevGeocode) as Record<string, unknown>)
      : { geocode_type: 'manual', result: {} as Record<string, unknown> }
  const result = geocode.result && typeof geocode.result === 'object' && !Array.isArray(geocode.result)
    ? (cloneJson(geocode.result) as Record<string, unknown>)
    : {}
  result.geometry = cloneJson(geometry)
  geocode.result = result
  markGeocodeAsManualEdit(geocode)
  return { geocode }
}

/** Overlay patch that updates formatted address only (no ``result.geometry``). */
export function buildGeocodePatchForFormattedAddress(
  mergedPlaceLocation: Record<string, unknown>,
  formattedAddress: string,
): Record<string, unknown> {
  const prevGeocode = mergedPlaceLocation.geocode
  const geocode: Record<string, unknown> =
    prevGeocode && typeof prevGeocode === 'object' && !Array.isArray(prevGeocode)
      ? {
          geocode_type:
            typeof (prevGeocode as Record<string, unknown>).geocode_type === 'string'
              ? (prevGeocode as Record<string, unknown>).geocode_type
              : 'manual',
        }
      : { geocode_type: 'manual' }
  const trimmed = formattedAddress.trim()
  const result: Record<string, unknown> = {}
  if (trimmed) {
    result.formatted_address = trimmed
    result.processed_str = trimmed
  }
  geocode.result = result
  return { geocode }
}

/** Overlay patch that clears ``geocode.result.geometry`` (review-only rows). */
export function buildGeocodePatchForClearGeometry(
  mergedPlaceLocation: Record<string, unknown>,
): Record<string, unknown> {
  const prevGeocode = mergedPlaceLocation.geocode
  const geocode =
    prevGeocode && typeof prevGeocode === 'object' && !Array.isArray(prevGeocode)
      ? (cloneJson(prevGeocode) as Record<string, unknown>)
      : { geocode_type: 'manual', result: {} as Record<string, unknown> }
  const result = geocode.result && typeof geocode.result === 'object' && !Array.isArray(geocode.result)
    ? (cloneJson(geocode.result) as Record<string, unknown>)
    : {}
  result.geometry = null
  geocode.result = result
  markGeocodeAsManualEdit(geocode)
  return { geocode }
}

export function applyGeometryToPlaceRow(
  place: Record<string, unknown>,
  geometry: Record<string, unknown> | null,
): Record<string, unknown> {
  const out = cloneJson(place) as Record<string, unknown>
  const prevGeocode = out.geocode
  const geocode =
    prevGeocode && typeof prevGeocode === 'object' && !Array.isArray(prevGeocode)
      ? (cloneJson(prevGeocode) as Record<string, unknown>)
      : { geocode_type: 'manual', result: {} as Record<string, unknown> }
  const result =
    geocode.result && typeof geocode.result === 'object' && !Array.isArray(geocode.result)
      ? (cloneJson(geocode.result) as Record<string, unknown>)
      : ({} as Record<string, unknown>)
  result.geometry = geometry === null ? null : cloneJson(geometry)
  geocode.result = result
  markGeocodeAsManualEdit(geocode)
  out.geocode = geocode
  return out
}

function mergeOverlayGeocodePatch(
  existing: unknown,
  patchGeocode: Record<string, unknown>,
): Record<string, unknown> {
  const prev =
    existing && typeof existing === 'object' && !Array.isArray(existing)
      ? (cloneJson(existing) as Record<string, unknown>)
      : { geocode_type: 'manual', result: {} as Record<string, unknown> }
  const patchResult = patchGeocode.result
  if (!patchResult || typeof patchResult !== 'object' || Array.isArray(patchResult)) {
    return patchGeocode
  }
  const prevResult =
    prev.result && typeof prev.result === 'object' && !Array.isArray(prev.result)
      ? (cloneJson(prev.result) as Record<string, unknown>)
      : ({} as Record<string, unknown>)
  const mergedResult = { ...prevResult }
  for (const [key, value] of Object.entries(patchResult as Record<string, unknown>)) {
    if (key === 'geometry') continue
    mergedResult[key] = value
  }
  if ('geometry' in (patchResult as Record<string, unknown>)) {
    mergedResult.geometry = (patchResult as Record<string, unknown>).geometry
  }
  return {
    ...prev,
    geocode_type:
      typeof patchGeocode.geocode_type === 'string'
        ? patchGeocode.geocode_type
        : (prev.geocode_type as string | undefined) ?? 'manual',
    result: mergedResult,
  }
}

/** Merge a place-shaped overlay fragment into an existing place dict. */
export function mergePlacePatchFragment(
  current: Record<string, unknown> | undefined,
  fragment: Record<string, unknown>,
): Record<string, unknown> {
  const merged: Record<string, unknown> =
    current && typeof current === 'object' && !Array.isArray(current)
      ? { ...(current as Record<string, unknown>) }
      : {}
  for (const [k, v] of Object.entries(fragment)) {
    if (k === 'geocode' && v && typeof v === 'object' && !Array.isArray(v)) {
      const patchGeo = v as Record<string, unknown>
      const patchResult = patchGeo.result
      const patchHasGeometry =
        patchResult &&
        typeof patchResult === 'object' &&
        !Array.isArray(patchResult) &&
        'geometry' in (patchResult as Record<string, unknown>)
      merged.geocode = patchHasGeometry
        ? patchGeo
        : mergeOverlayGeocodePatch(merged.geocode, patchGeo)
      continue
    }
    merged[k] = v
  }
  return merged
}

export function applyAnchorPatchFragment(
  draft: Record<string, unknown>,
  anchor: string,
  fragment: Record<string, unknown>,
): void {
  const n = normalizeOverlay(draft)
  const loc = n.locations as Record<string, unknown>
  const by = (loc.by_anchor as Record<string, unknown>) ?? {}
  by[anchor] = mergePlacePatchFragment(
    by[anchor] as Record<string, unknown> | undefined,
    fragment,
  )
  loc.by_anchor = by

  if (anchor.startsWith('user_place:')) {
    const ua = Array.isArray(loc.user_added) ? [...(loc.user_added as unknown[])] : []
    let found = false
    loc.user_added = ua.map((entry) => {
      if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return entry
      const row = entry as Record<string, unknown>
      if (row.id !== anchor) return entry
      found = true
      const locPayload =
        row.location && typeof row.location === 'object' && !Array.isArray(row.location)
          ? (row.location as Record<string, unknown>)
          : {}
      return {
        ...row,
        location: mergePlacePatchFragment(locPayload, fragment),
      }
    })
    if (!found) {
      loc.user_added = [
        ...ua,
        {
          id: anchor,
          location: mergePlacePatchFragment(undefined, fragment),
        },
      ]
    }
  }

  n.locations = loc
  Object.assign(draft, n)
}

export function newUserPlaceId(): string {
  const u =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `user_place:${u}`
}

export function appendUserPlacePoint(
  draft: Record<string, unknown>,
  lng: number,
  lat: number,
  description = 'New place',
): string {
  const n = normalizeOverlay(draft)
  const loc = n.locations as Record<string, unknown>
  const ua = Array.isArray(loc.user_added) ? [...(loc.user_added as unknown[])] : []
  const id = newUserPlaceId()
  const geometry: GeoJsonGeometry = { type: 'Point', coordinates: [lng, lat] }
  ua.push({
    id,
    location: {
      description,
      geocode: {
        geocode_type: 'manual',
        result: { geometry },
      },
    },
  })
  loc.user_added = ua
  n.locations = loc
  Object.assign(draft, n)
  return id
}

export function appendUserPlaceRectangle(
  draft: Record<string, unknown>,
  ring: [number, number][],
  description = 'New place',
): string {
  const n = normalizeOverlay(draft)
  const loc = n.locations as Record<string, unknown>
  const ua = Array.isArray(loc.user_added) ? [...(loc.user_added as unknown[])] : []
  const id = newUserPlaceId()
  const geometry: GeoJsonGeometry = { type: 'Polygon', coordinates: [ring] }
  ua.push({
    id,
    location: {
      description,
      geocode: {
        geocode_type: 'manual',
        result: { geometry },
      },
    },
  })
  loc.user_added = ua
  n.locations = loc
  Object.assign(draft, n)
  return id
}

export function shallowMergePlacePatch(
  location: Record<string, unknown>,
  patch: Record<string, unknown> | undefined | null,
): Record<string, unknown> {
  if (!patch) return location
  return { ...location, ...patch }
}

export type LeafletFeatureCollections = {
  points: { type: 'FeatureCollection'; features: unknown[] }
  polygons: { type: 'FeatureCollection'; features: unknown[] }
}

export function emptyFeatureCollections(): LeafletFeatureCollections {
  return {
    points: { type: 'FeatureCollection', features: [] },
    polygons: { type: 'FeatureCollection', features: [] },
  }
}

/** Remove static polygon layers for the selected place so the draggable rectangle editor receives pointer events. */
export function stripSelectedVerificationPolygonsForEdit(
  collections: LeafletFeatureCollections,
  selectedAnchor: string,
): LeafletFeatureCollections {
  const stripIds = new Set([selectedAnchor, `${selectedAnchor}__draft`])
  return {
    points: collections.points,
    polygons: {
      type: 'FeatureCollection',
      features: collections.polygons.features.filter((f) => {
        const feat = f as { id?: string; properties?: { id?: string } }
        const id = feat.id ?? feat.properties?.id
        return typeof id !== 'string' || !stripIds.has(id)
      }),
    },
  }
}

function pushGeometryFeatures(
  collections: LeafletFeatureCollections,
  anchor: string,
  geometry: Record<string, unknown> | null,
  group: string,
  label: string,
): void {
  if (!geometry) return
  const t = geometry.type
  const desc = label
  if (t === 'Point' && Array.isArray(geometry.coordinates) && geometry.coordinates.length === 2) {
    collections.points.features.push({
      type: 'Feature',
      id: anchor,
      properties: { id: anchor, label: desc, group },
      geometry: { type: 'Point', coordinates: geometry.coordinates },
    })
    return
  }
  if (
    (t === 'Polygon' || t === 'MultiPolygon') &&
    Array.isArray(geometry.coordinates) &&
    geometry.coordinates.length > 0
  ) {
    collections.polygons.features.push({
      type: 'Feature',
      id: anchor,
      properties: { id: anchor, label: desc, group },
      geometry: { type: t, coordinates: geometry.coordinates },
    })
  }
}

/** True when overlay ``by_anchor`` geometry for ``anchor`` differs between draft and saved baseline. */
export function overlayAnchorGeometryChanged(
  draftOverlay: Record<string, unknown>,
  baselineOverlay: Record<string, unknown>,
  anchor: string,
): boolean {
  const dLoc = normalizeOverlay(draftOverlay).locations as Record<string, unknown>
  const bLoc = normalizeOverlay(baselineOverlay).locations as Record<string, unknown>
  const dBy = (dLoc.by_anchor as Record<string, unknown>) ?? {}
  const bBy = (bLoc.by_anchor as Record<string, unknown>) ?? {}
  const dPatch = dBy[anchor]
  const bPatch = bBy[anchor]
  const gDraft =
    dPatch && typeof dPatch === 'object' && !Array.isArray(dPatch)
      ? extractGeometryFromPlace(dPatch as Record<string, unknown>)
      : null
  const gBaseline =
    bPatch && typeof bPatch === 'object' && !Array.isArray(bPatch)
      ? extractGeometryFromPlace(bPatch as Record<string, unknown>)
      : null
  return JSON.stringify(gDraft) !== JSON.stringify(gBaseline)
}

/**
 * Build Leaflet feature collections for merged rows. When ``selectedAnchor`` is set, only that
 * place is drawn. Linked rows may show model baseline under merged geometry only while geometry
 * is actively being edited or the overlay still has unsaved geometry for that anchor.
 */
export function buildVerificationLeafletCollections(params: {
  mergedRows: Array<Record<string, unknown>>
  baselineByAnchor: Map<string, Record<string, unknown>>
  selectedAnchor: string | null
  /** When true, the selected place shows only the in-progress draft (no baseline underlay). */
  geometryEditing?: boolean
  /** When true, linked rows with differing overlay geometry show model baseline + draft layers. */
  unsavedGeometryOverlay?: boolean
}): LeafletFeatureCollections {
  const out = emptyFeatureCollections()
  for (const row of params.mergedRows) {
    const anchor = typeof row.anchor === 'string' ? row.anchor : ''
    if (!anchor) continue
    if (params.selectedAnchor !== null && params.selectedAnchor !== anchor) {
      continue
    }
    const loc = row.location as Record<string, unknown> | undefined
    if (!loc) continue
    if (loc.geocode_region_mismatch === true || loc.geocode_qa_code === 'geocode_region_mismatch') {
      continue
    }
    const label = typeof loc.description === 'string' ? loc.description : anchor
    const gMerged = extractGeometryFromPlace(loc)
    if (!gMerged) continue
    const base = params.baselineByAnchor.get(anchor)
    const gBase = base ? extractGeometryFromPlace(base) : null
    const linked = isLocationLinkedToStylebookCanonical(loc)
    const editingThisPlace = params.geometryEditing === true && params.selectedAnchor === anchor
    if (
      linked &&
      !editingThisPlace &&
      params.unsavedGeometryOverlay === true &&
      gBase &&
      gMerged &&
      JSON.stringify(gBase) !== JSON.stringify(gMerged)
    ) {
      pushGeometryFeatures(out, `${anchor}__baseline`, gBase, 'verification-baseline', `${label} (saved map)`)
      pushGeometryFeatures(out, `${anchor}__draft`, gMerged, 'verification-draft', `${label} (your edits)`)
    } else {
      const group = params.selectedAnchor === anchor ? 'verification-selected' : 'verification-place'
      pushGeometryFeatures(out, anchor, gMerged, group, label)
    }
  }
  return out
}

export function isApiOverlayGeometryError(error: unknown): boolean {
  if (!(error instanceof Error)) return false
  const m = error.message
  return /\b400\b/.test(m) && m.includes('overlay_geometry_invalid')
}
