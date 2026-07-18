import { describe, expect, it } from "vitest"

import {
  bboxFromCorners,
  bboxToValue,
  cellAtPoint,
  cellResolution,
  cellsForBounds,
  parseBbox,
  validCenter,
} from "./mapSelection"

describe("map selection helpers", () => {
  it("normalizes and serializes bounding boxes in API coordinate order", () => {
    const bbox = bboxFromCorners(
      { lat: 42, lng: -87.5 },
      { lat: 41.7, lng: -87.8 },
    )

    expect(bbox).toEqual({
      minLng: -87.8,
      minLat: 41.7,
      maxLng: -87.5,
      maxLat: 42,
    })
    expect(bboxToValue(bbox)).toBe("-87.8,41.7,-87.5,42")
    expect(parseBbox("-87.8, 41.7, -87.5, 42")).toEqual(bbox)
    expect(parseBbox("-87.5,41.7,-87.8,42")).toBeNull()
  })

  it("validates point coordinates", () => {
    expect(validCenter("41.878", "-87.63")).toEqual({
      lat: 41.878,
      lng: -87.63,
    })
    expect(validCenter("91", "-87.63")).toBeNull()
    expect(validCenter("", "")).toBeNull()
  })

  it("creates selectable H3 cells at the requested resolution", () => {
    const cell = cellAtPoint(41.878, -87.63, 8)
    expect(cellResolution(cell)).toBe(8)
    expect(
      cellsForBounds(
        { south: 41.86, north: 41.9, west: -87.66, east: -87.6 },
        8,
      ),
    ).toContain(cell)
  })
})
