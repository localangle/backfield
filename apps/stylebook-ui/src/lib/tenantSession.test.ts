import { describe, expect, it, vi } from "vitest"
import {
  handleTenantResponse,
  ORGANIZATION_SELECTION_REQUIRED_EVENT,
  PASSWORD_CHANGE_REQUIRED_EVENT,
} from "@backfield/ui/tenantSession"

describe("tenant session responses", () => {
  it("announces an organization chooser response", async () => {
    const listener = vi.fn()
    window.addEventListener(ORGANIZATION_SELECTION_REQUIRED_EVENT, listener)
    const response = new Response(
      JSON.stringify({
        detail: { code: "organization_selection_required" },
      }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    )
    expect(await handleTenantResponse(response)).toBe(response)
    expect(listener).toHaveBeenCalledOnce()
    window.removeEventListener(ORGANIZATION_SELECTION_REQUIRED_EVENT, listener)
  })

  it("ignores unrelated conflicts", async () => {
    const listener = vi.fn()
    window.addEventListener(ORGANIZATION_SELECTION_REQUIRED_EVENT, listener)
    await handleTenantResponse(
      new Response(JSON.stringify({ detail: "conflict" }), {
        status: 409,
        headers: { "Content-Type": "application/json" },
      }),
    )
    expect(listener).not.toHaveBeenCalled()
    window.removeEventListener(ORGANIZATION_SELECTION_REQUIRED_EVENT, listener)
  })

  it("announces a required password change response", async () => {
    const listener = vi.fn()
    window.addEventListener(PASSWORD_CHANGE_REQUIRED_EVENT, listener)
    const response = new Response(
      JSON.stringify({
        detail: { code: "password_change_required" },
      }),
      { status: 403, headers: { "Content-Type": "application/json" } },
    )
    expect(await handleTenantResponse(response)).toBe(response)
    expect(listener).toHaveBeenCalledOnce()
    window.removeEventListener(PASSWORD_CHANGE_REQUIRED_EVENT, listener)
  })
})
