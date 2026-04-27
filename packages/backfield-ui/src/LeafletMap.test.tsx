import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { LeafletMap } from "./LeafletMap"

describe("LeafletMap", () => {
  it("renders stable empty state for empty inputs", () => {
    const { getByText } = render(<LeafletMap points={null} polygons={null} />)
    expect(getByText("No geographic features.")).toBeInTheDocument()
  })

  it("does not crash on invalid FeatureCollection shapes", () => {
    const bad: any = { type: "FeatureCollection", features: [null, 123, { type: "Feature" }] }
    const { getAllByText } = render(<LeafletMap points={bad} polygons={bad} />)
    // It may render empty-state after normalization; the key is “no crash”.
    expect(getAllByText("No geographic features.").length).toBeGreaterThan(0)
  })
})

