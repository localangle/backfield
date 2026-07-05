import { describe, expect, it } from "vitest"
import { duplicateSearchQuery, isMaterialDuplicateLabel } from "@/lib/similarCanonicalMatch"

describe("isMaterialDuplicateLabel", () => {
  it("matches identical labels modulo case and whitespace", () => {
    expect(isMaterialDuplicateLabel("Kentucky", "  kentucky ")).toBe(true)
  })

  it("matches a label against the same label with a trailing qualifier", () => {
    expect(isMaterialDuplicateLabel("Kentucky", "Kentucky, US")).toBe(true)
    expect(isMaterialDuplicateLabel("Chicago, IL", "Chicago, IL, USA")).toBe(true)
  })

  it("matches modulo a leading 'The'", () => {
    expect(isMaterialDuplicateLabel("The University of Chicago", "University of Chicago")).toBe(
      true,
    )
  })

  it("matches modulo periods in abbreviations", () => {
    expect(isMaterialDuplicateLabel("St. Louis, MO", "St Louis, MO")).toBe(true)
  })

  it("does not match containment with a different head", () => {
    expect(
      isMaterialDuplicateLabel("Chicago, IL", "O'Hare International Airport, Chicago, IL"),
    ).toBe(false)
  })

  it("does not match same-length labels with different qualifiers", () => {
    expect(isMaterialDuplicateLabel("Springfield, IL", "Springfield, MO")).toBe(false)
  })

  it("does not match different names", () => {
    expect(isMaterialDuplicateLabel("Jordan Walker", "Jordan Wilson")).toBe(false)
  })
})

describe("duplicateSearchQuery", () => {
  it("uses the head segment so both directions are searchable", () => {
    expect(duplicateSearchQuery("Kentucky, US")).toBe("kentucky")
    expect(duplicateSearchQuery("The University of Chicago")).toBe("university of chicago")
  })
})
