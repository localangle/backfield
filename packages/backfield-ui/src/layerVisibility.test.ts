import { describe, expect, it } from "vitest"
import { defaultVisibility, hideAll, layersFromFeatures, showAll, toggleLayer } from "./layerVisibility"

describe("layerVisibility", () => {
  it("extracts distinct layer ids from feature groups", () => {
    const layers = layersFromFeatures([{ group: "place" }, { group: "address" }, { group: "place" }, { group: "" }])
    expect(layers.map((l) => l.id)).toEqual(["address", "place"])
  })

  it("defaults to all visible", () => {
    const layers = [{ id: "a", label: "a" }, { id: "b", label: "b" }]
    expect(defaultVisibility(layers)).toEqual({ a: true, b: true })
  })

  it("toggles a layer without affecting others", () => {
    const vis = { a: true, b: true }
    expect(toggleLayer(vis, "a")).toEqual({ a: false, b: true })
  })

  it("showAll/hideAll set all known layers", () => {
    const layers = [{ id: "a", label: "a" }, { id: "b", label: "b" }]
    expect(hideAll(layers)).toEqual({ a: false, b: false })
    expect(showAll(layers)).toEqual({ a: true, b: true })
  })
})

