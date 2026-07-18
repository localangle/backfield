import { afterEach, describe, expect, it, vi } from "vitest"

import { playgroundHref } from "./platformUrls"

describe("Playground navigation", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it("uses the hosted Playground from a tenant host", () => {
    vi.stubGlobal("window", {
      location: { origin: "https://stylebook.cpm.backfield.news" },
    })

    expect(playgroundHref()).toBe(
      "https://playground.backfield.news/?organization=cpm",
    )
  })

  it("uses the local Playground while developing locally", () => {
    vi.stubGlobal("window", {
      location: { origin: "http://localhost:5175" },
    })

    expect(playgroundHref()).toBe("http://localhost:5176")
  })
})
