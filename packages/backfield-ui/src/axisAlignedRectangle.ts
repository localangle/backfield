export type LngLat = { lng: number; lat: number }

export type AxisAlignedBounds = {
  west: number
  south: number
  east: number
  north: number
}

function clampFinite(n: number, fallback: number): number {
  return Number.isFinite(n) ? n : fallback
}

export function normalizeLngLat(a: LngLat, b: LngLat): AxisAlignedBounds {
  const lng1 = clampFinite(a.lng, 0)
  const lat1 = clampFinite(a.lat, 0)
  const lng2 = clampFinite(b.lng, 0)
  const lat2 = clampFinite(b.lat, 0)

  const west = Math.min(lng1, lng2)
  const east = Math.max(lng1, lng2)
  const south = Math.min(lat1, lat2)
  const north = Math.max(lat1, lat2)

  return { west, south, east, north }
}

export function axisAlignedPolygonCoordinates(bounds: AxisAlignedBounds): [number, number][][] {
  const { west, south, east, north } = bounds
  const ring: [number, number][] = [
    [west, south],
    [east, south],
    [east, north],
    [west, north],
    [west, south],
  ]
  return [ring]
}

export function polygonFromAxisAlignedBounds(bounds: AxisAlignedBounds): { type: "Polygon"; coordinates: [number, number][][] } {
  return {
    type: "Polygon",
    coordinates: axisAlignedPolygonCoordinates(bounds),
  }
}

export function boundsFromPolygonGeometry(geometry: { type: "Polygon"; coordinates: number[][][] }): AxisAlignedBounds | null {
  const outer = geometry.coordinates?.[0]
  if (!Array.isArray(outer) || outer.length < 3) return null

  let west = Infinity
  let east = -Infinity
  let south = Infinity
  let north = -Infinity

  for (const coord of outer) {
    if (!Array.isArray(coord) || coord.length < 2) continue
    const lng = coord[0]
    const lat = coord[1]
    if (typeof lng !== "number" || typeof lat !== "number") continue
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue
    west = Math.min(west, lng)
    east = Math.max(east, lng)
    south = Math.min(south, lat)
    north = Math.max(north, lat)
  }

  if (!Number.isFinite(west) || !Number.isFinite(east) || !Number.isFinite(south) || !Number.isFinite(north)) return null
  if (west === east || south === north) return null
  return { west, south, east, north }
}

function nearlySameLngLat(a: [number, number], b: [number, number], eps: number): boolean {
  return Math.abs(a[0] - b[0]) <= eps && Math.abs(a[1] - b[1]) <= eps
}

/**
 * True when the polygon's outer ring matches the axis-aligned rectangle implied by its vertex bbox.
 * This intentionally rejects tilted/irregular polygons even if they share the same bbox.
 */
export function isAxisAlignedRectanglePolygon(geometry: { type: "Polygon"; coordinates: number[][][] }, eps = 1e-9): boolean {
  const bbox = boundsFromPolygonGeometry(geometry)
  if (!bbox) return false

  const expected = polygonFromAxisAlignedBounds(bbox)
  const outer = geometry.coordinates?.[0]
  if (!Array.isArray(outer) || outer.length < 4) return false

  const expectedRing = expected.coordinates[0]
  if (!Array.isArray(expectedRing) || expectedRing.length < 5) return false

  // Drop closing duplicate for set comparisons (rings may repeat first point at end).
  const actualVerts = outer
    .filter((c) => Array.isArray(c) && c.length >= 2)
    .slice(0, -1) as [number, number][]
  const expectedVerts = expectedRing
    .filter((c) => Array.isArray(c) && c.length >= 2)
    .slice(0, -1) as [number, number][]

  if (actualVerts.length !== 4 || expectedVerts.length !== 4) return false

  const uniqActual: [number, number][] = []
  for (const v of actualVerts) {
    if (!uniqActual.some((u) => nearlySameLngLat(u, v, eps))) uniqActual.push(v)
  }
  if (uniqActual.length !== 4) return false

  return expectedVerts.every((ev) => uniqActual.some((av) => nearlySameLngLat(av, ev, eps)))
}
