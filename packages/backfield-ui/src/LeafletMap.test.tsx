import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { LeafletMap, photonExtentToLeafletLatLngBounds } from "./LeafletMap"

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

describe("photonExtentToLeafletLatLngBounds", () => {
  it("derives south-west / north-east from Photon lon,lat,lon,lat extent (White House sample)", () => {
    const ext = [-77.0368541, 38.8977959, -77.0362517, 38.8974904] as const
    const [[south, west], [north, east]] = photonExtentToLeafletLatLngBounds(ext)
    expect(south).toBeCloseTo(38.8974904, 5)
    expect(north).toBeCloseTo(38.8977959, 5)
    expect(west).toBeCloseTo(-77.0368541, 5)
    expect(east).toBeCloseTo(-77.0362517, 5)
  })

  it("handles city-scale Photon extent (Chicago sample)", () => {
    const ext = [-87.9400876, 42.0230529, -87.5240812, 41.644531] as const
    const [[south, west], [north, east]] = photonExtentToLeafletLatLngBounds(ext)
    expect(south).toBeCloseTo(41.644531, 5)
    expect(north).toBeCloseTo(42.0230529, 5)
    expect(west).toBeCloseTo(-87.9400876, 5)
    expect(east).toBeCloseTo(-87.5240812, 5)
  })
})

