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

export function iterBaselinePlacesFromOutput(
  output: Record<string, unknown> | null | undefined,
): Array<{ anchor: string; nodeId: string; index: number; location: Record<string, unknown> }> {
  const rows: Array<{ anchor: string; nodeId: string; index: number; location: Record<string, unknown> }> = []
  if (!output || typeof output !== 'object') return rows
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
      let aid = place.id
      if (aid === undefined || aid === '') aid = place.mention_id
      const anchor =
        aid !== undefined && aid !== null && String(aid) !== '' ? String(aid) : `${nodeId}:${i}`
      rows.push({ anchor, nodeId, index: i, location: place })
    })
  }
  return rows
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
