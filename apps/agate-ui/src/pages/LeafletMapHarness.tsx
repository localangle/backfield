import { useMemo, useState } from "react"
import { LeafletMap } from "@backfield/ui"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"

export default function LeafletMapHarness() {
  const [lastClick, setLastClick] = useState<string>("(none)")

  const points = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: [
        {
          type: "Feature" as const,
          properties: { id: "point-chicago", label: "Chicago" },
          geometry: { type: "Point" as const, coordinates: [-87.6298, 41.8781] },
        },
        {
          type: "Feature" as const,
          properties: { id: "point-nyc", label: "NYC" },
          geometry: { type: "Point" as const, coordinates: [-74.006, 40.7128] },
        },
      ],
    }),
    [],
  )

  const polygons = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: [
        {
          type: "Feature" as const,
          properties: { id: "poly-rectangle" },
          geometry: {
            type: "Polygon" as const,
            coordinates: [
              [
                [-87.72, 41.84],
                [-87.56, 41.84],
                [-87.56, 41.92],
                [-87.72, 41.92],
                [-87.72, 41.84],
              ],
            ],
          },
        },
        {
          type: "Feature" as const,
          properties: { id: "poly-triangle" },
          geometry: {
            type: "Polygon" as const,
            coordinates: [
              [
                [-74.08, 40.70],
                [-73.92, 40.70],
                [-74.00, 40.80],
                [-74.08, 40.70],
              ],
            ],
          },
        },
      ],
    }),
    [],
  )

  return (
    <div className="container mx-auto p-6 space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Leaflet map harness</CardTitle>
          <CardDescription>Dev-only page to validate LeafletMap rendering and click events.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-sm text-muted-foreground">
            Last feature click: <span className="font-mono">{lastClick}</span>
          </div>
          <LeafletMap
            points={points as any}
            polygons={polygons as any}
            geocoder
            onFeatureClick={(e) => setLastClick(e.featureId ?? "(no id)")}
          />
        </CardContent>
      </Card>
    </div>
  )
}

