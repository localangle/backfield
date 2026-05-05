import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { AppMessageProvider } from "@/components/AppMessageProvider"
import ImportLocations from "@/pages/ImportLocations"

describe("ImportLocations", () => {
  it("renders and reads project query param", () => {
    render(
      <AppMessageProvider>
        <MemoryRouter
          initialEntries={["/stylebook/demo-sb/import/locations?project=demo-proj"]}
        >
          <Routes>
            <Route
              path="/stylebook/:stylebookSlug/import/locations"
              element={<ImportLocations />}
            />
          </Routes>
        </MemoryRouter>
      </AppMessageProvider>,
    )

    expect(screen.getByText("Import locations (GeoJSON)")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Back to canonicals" }).getAttribute("href")).toContain(
      "/stylebook/demo-sb/locations/canonical?project=demo-proj",
    )
  })
})

