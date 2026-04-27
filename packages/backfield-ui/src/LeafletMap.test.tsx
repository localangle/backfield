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

  it("renders with point editing enabled", () => {
    const points: any = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { id: "canonical", label: "Canonical" },
          geometry: { type: "Point", coordinates: [-87.6298, 41.8781] },
        },
      ],
    }
    render(
      <LeafletMap
        points={points}
        polygons={null}
        showPopups={false}
        editablePoint={{ featureId: "canonical", onChange: () => {} }}
      />,
    )
  })

  it("keeps hook order when clearing data after showing the map (e.g. delete geometry)", () => {
    const points: any = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { id: "canonical" },
          geometry: { type: "Point", coordinates: [-87.6298, 41.8781] },
        },
      ],
    }
    const { rerender } = render(
      <LeafletMap
        points={points}
        polygons={null}
        showPopups={false}
        editablePoint={{ featureId: "canonical", onChange: () => {} }}
      />,
    )
    rerender(<LeafletMap points={null} polygons={null} showPopups={false} editablePoint={null} />)
  })

  it("renders an interactive map in rectangle draw mode even with no features", () => {
    render(
      <LeafletMap
        points={null}
        polygons={null}
        showPopups={false}
        fitToData={false}
        rectangleDraw={{
          enabled: true,
          onPreview: () => {},
          onCommit: () => {},
        }}
      />,
    )
  })

  it("renders an interactive map when interactiveWhenEmpty (add-point style UX)", () => {
    render(
      <LeafletMap
        points={null}
        polygons={null}
        showPopups={false}
        fitToData={false}
        interactiveWhenEmpty
      />,
    )
  })
})

