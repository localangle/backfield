import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ForcedPasswordChange } from "./ForcedPasswordChange"

describe("ForcedPasswordChange", () => {
  afterEach(cleanup)

  it("requires matching passwords and completes after a successful change", async () => {
    const changePassword = vi.fn().mockResolvedValue(undefined)
    const onComplete = vi.fn().mockResolvedValue(undefined)
    render(
      <ForcedPasswordChange
        changePassword={changePassword}
        onComplete={onComplete}
        onLogout={vi.fn()}
      />,
    )

    fireEvent.change(screen.getByLabelText("Temporary password"), {
      target: { value: "temporary-secret" },
    })
    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "new-secret-one" },
    })
    fireEvent.change(screen.getByLabelText("Confirm new password"), {
      target: { value: "different-secret" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save new password" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "New passwords do not match.",
    )
    expect(changePassword).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText("Confirm new password"), {
      target: { value: "new-secret-one" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save new password" }))
    await waitFor(() => {
      expect(changePassword).toHaveBeenCalledWith(
        "temporary-secret",
        "new-secret-one",
      )
      expect(onComplete).toHaveBeenCalledOnce()
    })
  })

  it("keeps the form visible when the password change fails", async () => {
    const changePassword = vi.fn().mockRejectedValue(new Error("Current password is incorrect"))
    render(
      <ForcedPasswordChange
        changePassword={changePassword}
        onComplete={vi.fn()}
        onLogout={vi.fn()}
      />,
    )
    fireEvent.change(screen.getByLabelText("Temporary password"), {
      target: { value: "wrong-secret" },
    })
    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "new-secret-one" },
    })
    fireEvent.change(screen.getByLabelText("Confirm new password"), {
      target: { value: "new-secret-one" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save new password" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Current password is incorrect",
    )
  })

  it("offers logout without submitting the password form", () => {
    const changePassword = vi.fn()
    const onLogout = vi.fn()
    render(
      <ForcedPasswordChange
        changePassword={changePassword}
        onComplete={vi.fn()}
        onLogout={onLogout}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: "Log out" }))
    expect(onLogout).toHaveBeenCalledOnce()
    expect(changePassword).not.toHaveBeenCalled()
  })
})
