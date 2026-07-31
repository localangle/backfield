import { describe, expect, it } from "vitest"
import { augmentStylebookApiPath } from "@/lib/stylebook-api/client"
import { parseStylebookSlugFromPath } from "@/lib/stylebookPaths"

describe("organization-scoped Stylebook paths", () => {
  it("parses a catalog slug after the organization prefix", () => {
    expect(
      parseStylebookSlugFromPath("/org/daily/stylebook/investigations/locations/canonical"),
    ).toBe("investigations")
  })

  it("augments API paths from an organization-scoped browser URL", () => {
    window.history.replaceState(
      null,
      "",
      "/org/daily/stylebook/investigations/locations/canonical",
    )
    expect(augmentStylebookApiPath("/v1/candidates?project_slug=news")).toBe(
      "/v1/candidates?project_slug=news&stylebook_slug=investigations",
    )
  })
})
