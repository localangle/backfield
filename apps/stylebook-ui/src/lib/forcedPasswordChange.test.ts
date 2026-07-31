import { describe, expect, it } from "vitest"
import { shouldForcePasswordChange } from "@backfield/ui/passwordChangeGate"

describe("Stylebook forced password change gate", () => {
  it("blocks product rendering after organization selection", () => {
    expect(
      shouldForcePasswordChange({
        loading: false,
        isAuthenticated: true,
        mustChangePassword: true,
      }),
    ).toBe(true)
  })

  it("waits for restored-session loading to finish", () => {
    expect(
      shouldForcePasswordChange({
        loading: true,
        isAuthenticated: true,
        mustChangePassword: true,
      }),
    ).toBe(false)
  })
})
