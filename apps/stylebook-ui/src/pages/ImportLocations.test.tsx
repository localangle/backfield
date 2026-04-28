import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { AppMessageProvider } from "@/components/AppMessageProvider"
import ImportLocations from "@/pages/ImportLocations"

describe("ImportLocations", () => {
  it("renders and reads project query param", () => {
    render(
      <AppMessageProvider>
        <MemoryRouter initialEntries={["/import/locations?project=demo-proj"]}>
          <ImportLocations />
        </MemoryRouter>
      </AppMessageProvider>,
    )

    expect(screen.getByText("Import locations (GeoJSON)")).toBeInTheDocument()
    expect(screen.getByText("demo-proj")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Back to canonicals" }).getAttribute("href")).toContain(
      "/locations/canonical?project=demo-proj",
    )
  })
})

