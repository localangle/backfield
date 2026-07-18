import { describe, expect, it } from "vitest"

import {
  deriveApiOrigin,
  normalizeOrganizationSlug,
  organizationSlugFromPlaygroundHost,
  validateOrganizationSlug,
} from "./origin"

describe("organization API origin", () => {
  it("derives only the organization API hostname", () => {
    expect(deriveApiOrigin(" Local-Angle ")).toBe("https://api.local-angle.backfield.news")
  })

  it("normalizes and rejects unsafe slugs", () => {
    expect(normalizeOrganizationSlug("  News-Room  ")).toBe("news-room")
    expect(validateOrganizationSlug("news.example.com")).toBeDefined()
    expect(validateOrganizationSlug("-news")).toBeDefined()
    expect(() => deriveApiOrigin("https://other.example")).toThrow()
  })

  it("infers the organization only from a tenant Playground hostname", () => {
    expect(organizationSlugFromPlaygroundHost("playground.local-angle.backfield.news")).toBe(
      "local-angle",
    )
    expect(organizationSlugFromPlaygroundHost("playground.backfield.news")).toBe("")
    expect(organizationSlugFromPlaygroundHost("developer-tools.example.test")).toBe("")
  })
})
