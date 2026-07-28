import { describe, expect, it } from "vitest"

import { resolveUiOrigin, swapUiHostname } from "./siblingUiOrigin"

describe("swapUiHostname", () => {
  it("maps production and staging Backfield hosts", () => {
    expect(swapUiHostname("agate.cpm.backfield.news", "stylebook")).toBe(
      "stylebook.cpm.backfield.news",
    )
    expect(swapUiHostname("stylebook.cpm.backfield.news", "agate")).toBe(
      "agate.cpm.backfield.news",
    )
    expect(swapUiHostname("agate.canary.stg.backfield.news", "stylebook")).toBe(
      "stylebook.canary.stg.backfield.news",
    )
    expect(swapUiHostname("agate.canary.stg.backfield.news", "playground")).toBe(
      "playground.canary.stg.backfield.news",
    )
    expect(swapUiHostname("stylebook.cpm.backfield.news", "playground")).toBe(
      "playground.cpm.backfield.news",
    )
  })

  it("leaves non-split hosts unchanged", () => {
    expect(swapUiHostname("localhost", "stylebook")).toBe("localhost")
    expect(swapUiHostname("app.example.com", "agate")).toBe("app.example.com")
  })
})

describe("resolveUiOrigin", () => {
  it("prefers explicit env overrides", () => {
    expect(
      resolveUiOrigin({
        envOverride: "https://stylebook.example.com/",
        currentOrigin: "https://agate.cpm.backfield.news",
        targetApp: "stylebook",
      }),
    ).toBe("https://stylebook.example.com")
  })

  it("derives sibling origins for shared multi-client artifacts", () => {
    expect(
      resolveUiOrigin({
        envOverride: "",
        currentOrigin: "https://agate.cpm.backfield.news",
        targetApp: "stylebook",
      }),
    ).toBe("https://stylebook.cpm.backfield.news")

    expect(
      resolveUiOrigin({
        currentOrigin: "https://stylebook.canary.stg.backfield.news",
        targetApp: "agate",
      }),
    ).toBe("https://agate.canary.stg.backfield.news")
  })

  it("keeps same-origin fallback for local and custom hosts", () => {
    expect(
      resolveUiOrigin({
        currentOrigin: "http://localhost:5173",
        targetApp: "stylebook",
      }),
    ).toBe("http://localhost:5173")
  })
})
