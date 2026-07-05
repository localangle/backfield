import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"

import { StylebookHomeTabs } from "@/components/StylebookHomeTabs"

describe("StylebookHomeTabs", () => {
  it("renders Recent tab link beside Entities and Review", () => {
    render(
      <MemoryRouter initialEntries={["/stylebook/demo-sb/locations/canonical?project=demo-proj"]}>
        <Routes>
          <Route path="/stylebook/:stylebookSlug/locations/canonical" element={<StylebookHomeTabs />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole("link", { name: "Entities" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Review" })).toBeInTheDocument()
    const recent = screen.getByRole("link", { name: "Recent" })
    expect(recent).toBeInTheDocument()
    expect(recent.getAttribute("href")).toContain("/stylebook/demo-sb/recent?project=demo-proj")
  })
})
