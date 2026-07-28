import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"

import ParameterField from "./ParameterField"

describe("ParameterField", () => {
  afterEach(cleanup)

  it("places curated helper text below the control without repeating defaults", () => {
    const { container } = render(
      <ParameterField
        id="minimum-mentions"
        name="min_mentions"
        schema={{ type: "integer", default: 0 }}
        presentation={{
          control: "number",
          helperText: "Only include records with linked mentions.",
          typeLabel: "Integer",
        }}
        value=""
        origin="https://api.example.com"
        projectSlug=""
        apiKey=""
        onChange={() => undefined}
      />,
    )

    const field = container.querySelector(".parameter-field")
    const control = container.querySelector(".parameter-control")
    const helper = screen.getByText("Only include records with linked mentions.")
    const helperSlot = helper.closest(".parameter-description-slot")

    expect(field).not.toBeNull()
    expect(control).not.toBeNull()
    expect(helperSlot).not.toBeNull()
    expect(
      Array.from(field?.children ?? []).indexOf(control as Element),
    ).toBeLessThan(Array.from(field?.children ?? []).indexOf(helperSlot as Element))
    expect(screen.queryByText("Default: 0")).not.toBeInTheDocument()
  })
})
