import { describe, expect, it } from "vitest"
import { shouldForcePasswordChange } from "@backfield/ui/passwordChangeGate"

describe("Agate forced password change gate", () => {
  it("blocks product rendering for a restored flagged session", () => {
    expect(
      shouldForcePasswordChange({
        loading: false,
        isAuthenticated: true,
        mustChangePassword: true,
      }),
    ).toBe(true)
  })

  it("allows product rendering after the flag clears", () => {
    expect(
      shouldForcePasswordChange({
        loading: false,
        isAuthenticated: true,
        mustChangePassword: false,
      }),
    ).toBe(false)
  })
})
