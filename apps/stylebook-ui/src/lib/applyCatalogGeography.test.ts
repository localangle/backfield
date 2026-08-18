import { describe, expect, it } from "vitest"

import { defaultSelectedSavedPlaceIds } from "./applyCatalogGeography"

describe("defaultSelectedSavedPlaceIds", () => {
  it("selects only saved places suggested for catalog geography", () => {
    expect(
      defaultSelectedSavedPlaceIds([
        { id: 1, suggested_for_geometry: true },
        { id: 2, suggested_for_geometry: false },
        { id: 3 },
        { id: 4, suggested_for_geometry: true },
      ]),
    ).toEqual([1, 4])
  })
})
