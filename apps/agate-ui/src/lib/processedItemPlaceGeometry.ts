/**
 * Processed-item verification: place geometry helpers (overlay v1, LeafletMap parity).
 * See ``docs/API.md`` → *Processed item location overlay (v1)* → *Geometry*.
 */

import {
  isLocationLinkedToStylebookCanonical,
  normalizeOverlay,
} from './processedItemVerificationOverlay'

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

/** Client-side guard aligned with ``processed_item_overlay_validate`` (subset). */
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

function anchorForPlaceDict(place: Record<string, unknown>, nodeId: string, index: number): string {
  let aid = place.id
  if (aid === undefined || aid === '') aid = place.mention_id
  return aid !== undefined && aid !== null && String(aid) !== '' ? String(aid) : `${nodeId}:${index}`
}

function iterRowsFromLocations(
  output: Record<string, unknown>,
): Array<{ anchor: string; nodeId: string; index: number; location: Record<string, unknown> }> {
  const rows: Array<{ anchor: string; nodeId: string; index: number; location: Record<string, unknown> }> = []
  for (const [nodeId, payload] of Object.entries(output)) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) continue
    const p = payload as Record<string, unknown>
    let rawLocs = p.locations
    if (rawLocs !== undefined && rawLocs !== null && typeof rawLocs === 'object' && !Array.isArray(rawLocs)) {
      const inner = (rawLocs as Record<string, unknown>).locations
      if (Array.isArray(inner)) rawLocs = inner
    }
    if (!Array.isArray(rawLocs)) continue
    rawLocs.forEach((loc, i) => {
      if (!loc || typeof loc !== 'object' || Array.isArray(loc)) return
      const place = loc as Record<string, unknown>
      rows.push({ anchor: anchorForPlaceDict(place, nodeId, i), nodeId, index: i, location: place })
    })
  }
  return rows
}

function iterRowsFromPlaces(
  output: Record<string, unknown>,
): Array<{ anchor: string; nodeId: string; index: number; location: Record<string, unknown> }> {
  const rows: Array<{ anchor: string; nodeId: string; index: number; location: Record<string, unknown> }> = []
  for (const [nodeId, payload] of Object.entries(output)) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) continue
    const places = (payload as Record<string, unknown>).places
    if (!places || typeof places !== 'object' || Array.isArray(places)) continue
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
  }
  return rows
}

/** Baseline place rows for overlay math: ``locations`` arrays plus Geocode ``places`` (same anchor → geocode wins). */
export function iterBaselinePlacesFromOutput(
  output: Record<string, unknown> | null | undefined,
): Array<{ anchor: string; nodeId: string; index: number; location: Record<string, unknown> }> {
  if (!output || typeof output !== 'object') return []
  const byAnchor = new Map<
    string,
    { anchor: string; nodeId: string; index: number; location: Record<string, unknown> }
  >()
  const order: string[] = []
  const upsert = (row: { anchor: string; nodeId: string; index: number; location: Record<string, unknown> }) => {
    if (!byAnchor.has(row.anchor)) order.push(row.anchor)
    byAnchor.set(row.anchor, row)
  }
  for (const row of iterRowsFromLocations(output)) upsert(row)
  for (const row of iterRowsFromPlaces(output)) upsert(row)
  return order.map((a) => byAnchor.get(a)!)
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

/** True when the place row has geocoder output (geometry or a formatted line). */
export function isGeocodedPlace(place: Record<string, unknown> | null | undefined): boolean {
  if (!place || typeof place !== 'object') return false
  if (extractGeometryFromPlace(place)) return true
  const res = readGeocodeResult(place)
  if (!res) return false
  const fa = res.formatted_address ?? res.processed_str
  return typeof fa === 'string' && fa.trim().length > 0
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
  return { geocode }
}

export function applyAnchorPatchFragment(
  draft: Record<string, unknown>,
  anchor: string,
  fragment: Record<string, unknown>,
): void {
  const n = normalizeOverlay(draft)
  const loc = n.locations as Record<string, unknown>
  const by = (loc.by_anchor as Record<string, unknown>) ?? {}
  const cur = by[anchor]
  const merged: Record<string, unknown> =
    cur && typeof cur === 'object' && !Array.isArray(cur) ? { ...(cur as Record<string, unknown>) } : {}
  for (const [k, v] of Object.entries(fragment)) {
    merged[k] = v
  }
  by[anchor] = merged
  loc.by_anchor = by
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

/**
 * Build Leaflet feature collections for all merged rows. Linked rows with draft geometry
 * differing from model baseline emit two features (baseline + draft groups).
 */
export function buildVerificationLeafletCollections(params: {
  mergedRows: Array<Record<string, unknown>>
  baselineByAnchor: Map<string, Record<string, unknown>>
  selectedAnchor: string | null
}): LeafletFeatureCollections {
  const out = emptyFeatureCollections()
  for (const row of params.mergedRows) {
    const anchor = typeof row.anchor === 'string' ? row.anchor : ''
    if (!anchor) continue
    const loc = row.location as Record<string, unknown> | undefined
    if (!loc) continue
    const label = typeof loc.description === 'string' ? loc.description : anchor
    const gMerged = extractGeometryFromPlace(loc)
    const base = params.baselineByAnchor.get(anchor)
    const gBase = base ? extractGeometryFromPlace(base) : null
    const linked = isLocationLinkedToStylebookCanonical(loc)
    if (linked && gBase && gMerged && JSON.stringify(gBase) !== JSON.stringify(gMerged)) {
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
