import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  API_KEY_ACTIVE_SESSION_STORAGE,
  API_KEY_VAULT_SESSION_STORAGE,
  displayLabelForSecret,
  fetchAccessibleProjectApiKeyMetadata,
  forgetAllProjectApiKeys,
  projectApiKeyPrefix,
  readRememberedApiKeys,
  rememberApiKey,
  writeRememberedApiKeys,
} from "./projectApiKeys"

const KEY_ONE = `bfk_${"a".repeat(40)}`
const KEY_TWO = `bfk_${"b".repeat(40)}`

describe("project API key vault", () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("migrates a legacy single-key sessionStorage value into the vault", () => {
    sessionStorage.setItem(API_KEY_ACTIVE_SESSION_STORAGE, KEY_ONE)
    expect(readRememberedApiKeys()).toEqual([KEY_ONE])
  })

  it("reads the vault when both storage keys exist", () => {
    sessionStorage.setItem(API_KEY_ACTIVE_SESSION_STORAGE, KEY_TWO)
    sessionStorage.setItem(API_KEY_VAULT_SESSION_STORAGE, JSON.stringify([KEY_ONE, KEY_TWO]))
    expect(readRememberedApiKeys()).toEqual([KEY_ONE, KEY_TWO])
  })

  it("appends unique secrets and persists JSON without writing localStorage", () => {
    const localStorageWrite = vi.spyOn(window.localStorage, "setItem")
    const next = rememberApiKey(KEY_TWO, rememberApiKey(KEY_ONE, []))
    expect(next).toEqual([KEY_ONE, KEY_TWO])
    expect(rememberApiKey(KEY_ONE, next)).toEqual([KEY_ONE, KEY_TWO])
    writeRememberedApiKeys(next)
    expect(sessionStorage.getItem(API_KEY_VAULT_SESSION_STORAGE)).toBe(
      JSON.stringify([KEY_ONE, KEY_TWO]),
    )
    expect(localStorageWrite).not.toHaveBeenCalled()
  })

  it("clears the vault and active key together", () => {
    sessionStorage.setItem(API_KEY_ACTIVE_SESSION_STORAGE, KEY_ONE)
    writeRememberedApiKeys([KEY_ONE, KEY_TWO])
    forgetAllProjectApiKeys()
    expect(sessionStorage.getItem(API_KEY_ACTIVE_SESSION_STORAGE)).toBeNull()
    expect(sessionStorage.getItem(API_KEY_VAULT_SESSION_STORAGE)).toBeNull()
    expect(readRememberedApiKeys()).toEqual([])
  })

  it("labels remembered secrets from prefix metadata without exposing the secret", () => {
    const prefix = projectApiKeyPrefix(KEY_ONE)
    const label = displayLabelForSecret(KEY_ONE, [
      {
        prefix,
        label: "Local testing",
        projectId: 2,
        projectName: "Daily News",
        projectSlug: "daily-news",
      },
    ])
    expect(label).toContain("Daily News")
    expect(label).toContain("Local testing")
    expect(label).not.toContain(KEY_ONE)
    expect(displayLabelForSecret(KEY_TWO, [])).not.toContain(KEY_TWO)
  })

  it("fetches list metadata per accessible project and skips failures", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith("/v1/projects/2/api-keys")) {
        return new Response(
          JSON.stringify([
            {
              key_prefix: projectApiKeyPrefix(KEY_ONE),
              label: "Local testing",
              revoked_at: null,
            },
            {
              key_prefix: "bfk_revokedprefixxxxxxx",
              label: "Old key",
              revoked_at: "2026-01-01T00:00:00Z",
            },
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } },
        )
      }
      if (url.endsWith("/v1/projects/3/api-keys")) {
        return new Response(JSON.stringify({ detail: "Forbidden" }), { status: 403 })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    vi.stubGlobal("fetch", fetchMock)

    await expect(
      fetchAccessibleProjectApiKeyMetadata("http://localhost:8004", [
        { id: 2, name: "Daily News", slug: "daily-news" },
        { id: 3, name: "Hidden", slug: "hidden" },
      ]),
    ).resolves.toEqual([
      {
        prefix: projectApiKeyPrefix(KEY_ONE),
        label: "Local testing",
        projectId: 2,
        projectName: "Daily News",
        projectSlug: "daily-news",
      },
    ])
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8004/v1/projects/2/api-keys",
      expect.objectContaining({ credentials: "include" }),
    )
  })
})
