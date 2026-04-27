import { describe, expect, it } from "vitest"
import {
  boundsFromPolygonGeometry,
  isAxisAlignedRectanglePolygon,
  normalizeLngLat,
  polygonFromAxisAlignedBounds,
} from "./axisAlignedRectangle"

describe("axisAlignedRectangle", () => {
  it("normalizes bounds regardless of corner order", () => {
    expect(normalizeLngLat({ lng: 1, lat: 2 }, { lng: 3, lat: 4 })).toEqual({ west: 1, south: 2, east: 3, north: 4 })
    expect(normalizeLngLat({ lng: 3, lat: 4 }, { lng: 1, lat: 2 })).toEqual({ west: 1, south: 2, east: 3, north: 4 })
  })

  it("builds a closed ring polygon", () => {
    const poly = polygonFromAxisAlignedBounds({ west: -1, south: -2, east: 3, north: 4 })
    expect(poly.type).toBe("Polygon")
    const ring = poly.coordinates[0]
    expect(ring[0]).toEqual(ring[ring.length - 1])
    expect(ring[0]).toEqual([-1, -2])
    expect(ring[2]).toEqual([3, 4])
  })

  it("round-trips bounds from a simple rectangle polygon", () => {
    const poly = polygonFromAxisAlignedBounds({ west: 10, south: 20, east: 30, north: 40 })
    const b = boundsFromPolygonGeometry(poly)
    expect(b).toEqual({ west: 10, south: 20, east: 30, north: 40 })
  })

  it("detects axis-aligned rectangle polygons", () => {
    const poly = polygonFromAxisAlignedBounds({ west: 0, south: 0, east: 1, north: 1 })
    expect(isAxisAlignedRectanglePolygon(poly)).toBe(true)
  })

  it("rejects tilted rectangles that share the same bbox", () => {
    const tilted: any = {
      type: "Polygon",
      coordinates: [
        [
          [0, 0],
          [1, 0.1],
          [1, 1],
          [0, 0.9],
          [0, 0],
        ],
      ],
    }
    expect(isAxisAlignedRectanglePolygon(tilted)).toBe(false)
  })
})
