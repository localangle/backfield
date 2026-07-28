import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { UserAccountMenu } from "./UserAccountMenu"

describe("UserAccountMenu", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("shows the same account actions in every app", async () => {
    vi.stubGlobal("PointerEvent", MouseEvent)
    render(
      <UserAccountMenu
        userLabel="admin@backfield.news"
        onChangePassword={vi.fn()}
        onLogout={vi.fn()}
      />,
    )

    fireEvent.pointerDown(
      screen.getByRole("button", {
        name: "Account menu for admin@backfield.news",
      }),
      { button: 0, ctrlKey: false },
    )

    expect(await screen.findByText("admin@backfield.news")).toBeInTheDocument()
    expect(screen.getByRole("menuitem", { name: "Change password" })).toBeInTheDocument()
    expect(screen.getByRole("menuitem", { name: "Log out" })).toBeInTheDocument()
    expect(screen.getAllByRole("menuitem")).toHaveLength(2)
  })
})
