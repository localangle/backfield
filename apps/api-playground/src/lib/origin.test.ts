import { describe, expect, it } from "vitest"

import {
  deriveApiOrigin,
  deriveProductOrigin,
  deriveStylebookApiOrigin,
  normalizeOrganizationSlug,
  organizationSlugFromPlaygroundHost,
  parsePlaygroundHost,
  validateOrganizationSlug,
} from "./origin"

describe("organization API origin", () => {
  it("derives only the organization API hostname", () => {
    expect(deriveApiOrigin(" Local-Angle ")).toBe("https://api.local-angle.backfield.news")
    expect(deriveApiOrigin("canary", "stg.backfield.news")).toBe(
      "https://api.canary.stg.backfield.news",
    )
  })

  it("derives product and Stylebook API origins for staging", () => {
    expect(deriveProductOrigin("agate", "canary", "stg.backfield.news")).toBe(
      "https://agate.canary.stg.backfield.news",
    )
    expect(deriveStylebookApiOrigin("canary", "stg.backfield.news")).toBe(
      "https://stylebook.canary.stg.backfield.news/api/stylebook",
    )
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
    expect(organizationSlugFromPlaygroundHost("playground.canary.stg.backfield.news")).toBe(
      "canary",
    )
    expect(organizationSlugFromPlaygroundHost("playground.backfield.news")).toBe("")
    expect(organizationSlugFromPlaygroundHost("developer-tools.example.test")).toBe("")
  })

  it("parses production and staging Playground hosts", () => {
    expect(parsePlaygroundHost("playground.cpm.backfield.news")).toEqual({
      slug: "cpm",
      parentDomain: "backfield.news",
    })
    expect(parsePlaygroundHost("playground.canary.stg.backfield.news")).toEqual({
      slug: "canary",
      parentDomain: "stg.backfield.news",
    })
    expect(parsePlaygroundHost("playground.canary.backfield.news")).toEqual({
      slug: "canary",
      parentDomain: "backfield.news",
    })
    expect(parsePlaygroundHost("agate.canary.stg.backfield.news")).toBeNull()
  })
})
