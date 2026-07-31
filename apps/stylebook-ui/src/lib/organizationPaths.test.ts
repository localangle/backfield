import { describe, expect, it } from "vitest"
import { scopeOrganizationPath } from "../../../../packages/backfield-ui/src/organizationPaths"

describe("organization routes", () => {
  it("preserves a scoped Stylebook path", () => {
    expect(scopeOrganizationPath("/org/daily/stylebook/default", "", "daily")).toEqual({
      scopedPathname: "/stylebook/default",
      requestedOrganizationSlug: "daily",
      redirectPath: null,
    })
  })

  it("redirects a legacy Stylebook path after authentication", () => {
    expect(
      scopeOrganizationPath("/stylebook/default", "?project_scope=news", "daily").redirectPath,
    ).toBe("/org/daily/stylebook/default?project_scope=news")
  })
})
