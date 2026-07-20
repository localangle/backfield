import { afterEach, describe, expect, it, vi } from "vitest"

import { logoutSession } from "./session"

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
})
