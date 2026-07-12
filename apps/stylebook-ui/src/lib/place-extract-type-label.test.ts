import { describe, expect, it } from "vitest"

import { placeExtractTypeLabel } from "./place-extract-type-label"

describe("placeExtractTypeLabel organization types", () => {
  it("uses explicit organization labels", () => {
    expect(placeExtractTypeLabel("law_enforcement")).toBe("Law enforcement")
    expect(placeExtractTypeLabel("culture_arts")).toBe("Culture / arts")
    expect(placeExtractTypeLabel("religious_org")).toBe("Religious organization")
  })

  it("title-cases simple organization slugs", () => {
    expect(placeExtractTypeLabel("government")).toBe("Government")
    expect(placeExtractTypeLabel("school")).toBe("School")
  })
})
