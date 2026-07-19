import { afterEach, describe, expect, it, vi } from "vitest"

import { fetchMentionFacets } from "./api"

describe("public option discovery", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("maps mention facets into form option families", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(
          JSON.stringify({
            entity_types: ["person", "location"],
            natures: ["primary"],
            location_types: ["place"],
            person_types: ["public_official"],
            organization_types: ["government"],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    )

    await expect(
      fetchMentionFacets(
        "https://api.news.backfield.news",
        "daily-news",
        "project-key",
      ),
    ).resolves.toEqual({
      entityTypes: ["person", "location"],
      natures: ["primary"],
      locationTypes: ["place"],
      personTypes: ["public_official"],
      organizationTypes: ["government"],
    })
  })

  it("rejects malformed mention facet responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(JSON.stringify({ entity_types: "person" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    )

    await expect(
      fetchMentionFacets(
        "https://api.news.backfield.news",
        "daily-news",
        "project-key",
      ),
    ).rejects.toThrow("Mention facets response was invalid")
  })
})
