import { afterEach, describe, expect, it, vi } from "vitest"

import {
  fetchPlatformContext,
  logoutSession,
  SessionAuthRequiredError,
  switchOrganization,
} from "./session"

describe("Playground session", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("logs out through the tenant session host with browser credentials", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(null))
    vi.stubGlobal("fetch", fetchMock)

    // Cloud session/admin routes live on the Agate UI host, not api.*.
    await logoutSession("https://agate.newsroom.backfield.news")

    expect(fetchMock).toHaveBeenCalledWith(
      "https://agate.newsroom.backfield.news/v1/auth/logout",
      {
        method: "POST",
        credentials: "include",
        referrerPolicy: "no-referrer",
      },
    )
  })

  it("still resolves when the logout request cannot be confirmed", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new Error("offline")))

    await expect(logoutSession("https://agate.newsroom.backfield.news")).resolves.toBeUndefined()
  })

  it("requires a Backfield session before loading the signed-in shell", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Not authenticated" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    )

    await expect(
      fetchPlatformContext(
        "https://agate.newsroom.backfield.news",
        "https://stylebook-api.newsroom.backfield.news",
      ),
    ).rejects.toBeInstanceOf(SessionAuthRequiredError)
  })

  it("loads org map default viewport with the signed-in shell", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith("/v1/auth/me")) {
        return new Response(
          JSON.stringify({
            authenticated: true,
            email: "editor@example.com",
            organization_id: 7,
            organization_name: "Newsroom",
            organization_slug: "newsroom",
            org_role: "admin",
            organizations: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        )
      }
      if (url.endsWith("/v1/me/workspaces")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      }
      if (url.includes("/stylebooks")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      }
      if (url.endsWith("/v1/organizations/7/settings")) {
        return new Response(
          JSON.stringify({
            map_default_viewport: { lat: 41.88, lng: -87.63, zoom: 11 },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        )
      }
      return new Response(JSON.stringify({ detail: "not found" }), { status: 404 })
    })
    vi.stubGlobal("fetch", fetchMock)

    const context = await fetchPlatformContext(
      "https://agate.newsroom.backfield.news",
      "https://stylebook-api.newsroom.backfield.news",
    )

    expect(context.mapDefaultViewport).toEqual({
      lat: 41.88,
      lng: -87.63,
      zoom: 11,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      "https://agate.newsroom.backfield.news/v1/organizations/7/settings",
      expect.objectContaining({ credentials: "include" }),
    )
  })

  it("switches the active organization through the tenant session host", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(JSON.stringify({ success: true }), { status: 200 }))
    vi.stubGlobal("fetch", fetchMock)

    await switchOrganization("https://agate.newsroom.backfield.news", 2)

    expect(fetchMock).toHaveBeenCalledWith(
      "https://agate.newsroom.backfield.news/v1/auth/switch-organization",
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        referrerPolicy: "no-referrer",
        body: JSON.stringify({ organization_id: 2 }),
      },
    )
  })
})
