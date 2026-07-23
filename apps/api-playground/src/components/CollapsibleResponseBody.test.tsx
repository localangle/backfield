import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { CollapsibleResponseBody } from "./CollapsibleResponseBody"

describe("CollapsibleResponseBody", () => {
  it("collapses polygon geometry while leaving the surrounding response visible", () => {
    const body = JSON.stringify(
      {
        id: "edgewater",
        geometry_json: {
          type: "MultiPolygon",
          coordinates: [
            [
              [
                [-87.65, 41.99],
                [-87.64, 41.99],
                [-87.64, 42.0],
                [-87.65, 41.99],
              ],
            ],
          ],
        },
        label: "Edgewater",
      },
      null,
      2,
    )

    render(<CollapsibleResponseBody body={body} />)

    expect(screen.getByText(/"id": "edgewater"/)).toBeInTheDocument()
    expect(screen.getByText(/"label": "Edgewater"/)).toBeInTheDocument()
    const summary = screen.getByLabelText(
      "Show MultiPolygon geometry for geometry_json",
    )
    expect(summary).toHaveTextContent("MultiPolygon, 4 positions")
    const details = summary.closest("details")
    expect(details).not.toHaveAttribute("open")

    fireEvent.click(summary)
    expect(details).toHaveAttribute("open")
    expect(screen.getByText(/-87.65/)).toBeInTheDocument()
  })

  it("keeps non-JSON and JSON without polygon geometry as plain preformatted text", () => {
    const { rerender } = render(<CollapsibleResponseBody body="Plain response" />)
    expect(screen.getByText("Plain response").tagName).toBe("PRE")

    rerender(<CollapsibleResponseBody body={'{"items": []}'} />)
    expect(screen.getByText('{"items": []}').tagName).toBe("PRE")
  })
})
