import { describe, expect, it } from "vitest"
import { scopeOrganizationPath } from "../../../../packages/backfield-ui/src/organizationPaths"

describe("organization routes", () => {
  it("redirects an authenticated legacy path into the active organization", () => {
    expect(scopeOrganizationPath("/project/news", "?tab=runs", "daily")).toEqual({
      scopedPathname: "/project/news",
      requestedOrganizationSlug: null,
      redirectPath: "/org/daily/project/news?tab=runs",
    })
  })

  it("replaces an untrusted organization slug", () => {
    expect(scopeOrganizationPath("/org/other/runs", "", "daily").redirectPath).toBe(
      "/org/daily/runs",
    )
  })
})
