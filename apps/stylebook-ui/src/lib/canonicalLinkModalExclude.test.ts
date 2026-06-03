import { describe, expect, it } from "vitest"
import {
  buildCanonicalLinkExcludeIds,
  isExcludedCanonicalLinkTarget,
} from "./canonicalLinkModalExclude"

describe("canonicalLinkModalExclude", () => {
  it("merges linked and explicit exclude ids", () => {
    const ids = buildCanonicalLinkExcludeIds("linked-id", "page-id")
    expect(ids.has("linked-id")).toBe(true)
    expect(ids.has("page-id")).toBe(true)
  })

  it("matches canonical targets case-sensitively by trimmed string", () => {
    const ids = buildCanonicalLinkExcludeIds("abc", null)
    expect(isExcludedCanonicalLinkTarget("abc", ids)).toBe(true)
    expect(isExcludedCanonicalLinkTarget(" def ", ids)).toBe(false)
  })
})
