import {
  cellToBoundary,
  cellToLatLng,
  getResolution,
  isValidCell,
  latLngToCell,
  polygonToCells,
} from "h3-js"

export interface BoundingBox {
  minLng: number
  minLat: number
  maxLng: number
  maxLat: number
}

export interface MapCenter {
  lat: number
  lng: number
}

export const DEFAULT_MAP_CENTER: MapCenter = { lat: 41.878, lng: -87.63 }

export function spansAntimeridian(bbox: BoundingBox): boolean {
  return bbox.maxLng - bbox.minLng > 180
}

export function bboxFromCorners(a: MapCenter, b: MapCenter): BoundingBox | null {
  const bbox: BoundingBox = {
    minLng: Math.min(a.lng, b.lng),
    minLat: Math.min(a.lat, b.lat),
    maxLng: Math.max(a.lng, b.lng),
    maxLat: Math.max(a.lat, b.lat),
  }
  // Public API envelopes are non-wrapping; reject boxes that cross the antimeridian.
  if (spansAntimeridian(bbox)) return null
  return bbox
}

export function parseBbox(value: string): BoundingBox | null {
  const values = value.split(",").map((part) => Number(part.trim()))
  if (
    values.length !== 4 ||
    values.some((part) => !Number.isFinite(part)) ||
    values[0] >= values[2] ||
    values[1] >= values[3]
  ) {
    return null
  }
  const bbox: BoundingBox = {
    minLng: values[0],
    minLat: values[1],
    maxLng: values[2],
    maxLat: values[3],
  }
  if (spansAntimeridian(bbox)) return null
  return bbox
}

export function bboxToValue(bbox: BoundingBox): string {
  return [bbox.minLng, bbox.minLat, bbox.maxLng, bbox.maxLat]
    .map((value) => Number(value.toFixed(6)))
    .join(",")
}

export function bboxToLeafletBounds(
  bbox: BoundingBox,
): [[number, number], [number, number]] {
  return [
    [bbox.minLat, bbox.minLng],
    [bbox.maxLat, bbox.maxLng],
  ]
}

export function validCenter(latitude: string, longitude: string): MapCenter | null {
  if (!latitude.trim() || !longitude.trim()) return null
  const lat = Number(latitude)
  const lng = Number(longitude)
  if (
    !Number.isFinite(lat) ||
    !Number.isFinite(lng) ||
    Math.abs(lat) > 90 ||
    Math.abs(lng) > 180
  ) {
    return null
  }
  return { lat, lng }
}

export function cellResolution(cell: string): number | null {
  return isValidCell(cell) ? getResolution(cell) : null
}

export function centerFromCells(cells: string[]): MapCenter | null {
  const centers = cells
    .filter(isValidCell)
    .map((cell) => cellToLatLng(cell))
  if (!centers.length) return null
  return {
    lat: centers.reduce((sum, center) => sum + center[0], 0) / centers.length,
    lng: centers.reduce((sum, center) => sum + center[1], 0) / centers.length,
  }
}

export function cellBoundary(cell: string): [number, number][] {
  return cellToBoundary(cell) as [number, number][]
}

export function cellAtPoint(lat: number, lng: number, resolution: number): string {
  return latLngToCell(lat, lng, resolution)
}

export function cellsForBounds(
  bounds: { south: number; north: number; west: number; east: number },
  resolution: number,
  limit = 800,
): string[] {
  const ring: [number, number][] = [
    [bounds.west, bounds.south],
    [bounds.east, bounds.south],
    [bounds.east, bounds.north],
    [bounds.west, bounds.north],
    [bounds.west, bounds.south],
  ]
  return polygonToCells(ring, resolution, true).slice(0, limit)
}
