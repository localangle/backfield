import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { OrganizationSwitcher } from "@backfield/ui"

describe("OrganizationSwitcher", () => {
  afterEach(cleanup)

  it("offers organizations and switches from an accessible control", async () => {
    const onSwitch = vi.fn().mockResolvedValue(undefined)
    render(
      <OrganizationSwitcher
        organizationId={1}
        organizations={[
          { id: 1, name: "Daily", slug: "daily" },
          { id: 2, name: "Weekly", slug: "weekly" },
        ]}
        onSwitch={onSwitch}
      />,
    )
    fireEvent.change(screen.getByLabelText("Organization"), {
      target: { value: "2" },
    })
    await waitFor(() => expect(onSwitch).toHaveBeenCalledWith(2))
  })

  it("announces switch failures without rejecting the event handler", async () => {
    render(
      <OrganizationSwitcher
        organizationId={1}
        organizations={[
          { id: 1, name: "Daily", slug: "daily" },
          { id: 2, name: "Weekly", slug: "weekly" },
        ]}
        onSwitch={vi.fn().mockRejectedValue(new Error("network"))}
      />,
    )
    fireEvent.change(screen.getByLabelText("Organization"), {
      target: { value: "2" },
    })
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not switch organizations",
    )
  })
})
