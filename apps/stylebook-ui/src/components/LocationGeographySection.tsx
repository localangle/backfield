import { useCallback, useEffect, useMemo, useState } from "react"
import { useAppMessage } from "@/components/AppMessageProvider"
import SimpleGeoJsonGeometry from "@/components/SimpleGeoJsonGeometry"
import { updateCanonicalLocationGeometry } from "@/lib/stylebook-api/locations"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { GeometryEditLeafletMap } from "@backfield/ui/GeometryEditLeafletMap"
import {
  boundsFromPolygonGeometry,
  isAxisAlignedRectanglePolygon,
} from "@backfield/ui/axisAlignedRectangle"
import { Info, MousePointer, Square, Trash2 } from "lucide-react"

type GeoJsonGeometry =
  | { type: "Point"; coordinates: [number, number] }
  | { type: "Polygon"; coordinates: [number, number][][] }
  | { type: "MultiPolygon"; coordinates: [number, number][][][] }

function isPointGeometry(geometry: Record<string, unknown> | null): geometry is {
  type: "Point"
  coordinates: [number, number]
} {
  if (!geometry || typeof geometry !== "object") return false
  const g = geometry as Record<string, unknown>
  if (g.type !== "Point") return false
  const c = g.coordinates
  return Array.isArray(c) && c.length === 2 && typeof c[0] === "number" && typeof c[1] === "number"
}

function isPolygonGeometry(geometry: Record<string, unknown> | null): geometry is {
  type: "Polygon"
  coordinates: number[][][]
} {
  if (!geometry || typeof geometry !== "object") return false
  const g = geometry as Record<string, unknown>
  if (g.type !== "Polygon") return false
  const c = g.coordinates
  return Array.isArray(c) && c.length > 0
}

function isMultiPolygonGeometry(geometry: Record<string, unknown> | null): boolean {
  if (!geometry || typeof geometry !== "object") return false
  const g = geometry as Record<string, unknown>
  return g.type === "MultiPolygon"
}

function axisAlignedRectangleDraft(geometry: Record<string, unknown> | null): boolean {
  if (!isPolygonGeometry(geometry)) return false
  return isAxisAlignedRectanglePolygon(geometry)
}

function geometryToFeatureCollections(
  geometry: Record<string, unknown> | null,
  opts?: { featureId?: string; label?: string; group?: string },
): { points: unknown; polygons: unknown } {
  if (!geometry || typeof geometry !== "object") {
    return {
      points: { type: "FeatureCollection", features: [] },
      polygons: { type: "FeatureCollection", features: [] },
    }
  }

  const featureId = opts?.featureId ?? "canonical"
  const label = opts?.label ?? "Canonical"
  const group = opts?.group ?? "canonical"

  const g = geometry as Partial<GeoJsonGeometry>
  const type = typeof g.type === "string" ? g.type : null

  if (type === "Point" && Array.isArray(g.coordinates) && g.coordinates.length === 2) {
    const coords = g.coordinates as [number, number]
    return {
      points: {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            properties: { id: featureId, label, group },
            geometry: { type: "Point", coordinates: coords },
          },
        ],
      },
      polygons: { type: "FeatureCollection", features: [] },
    }
  }

  if (
    (type === "Polygon" || type === "MultiPolygon") &&
    Array.isArray(g.coordinates) &&
    g.coordinates.length > 0
  ) {
    return {
      points: { type: "FeatureCollection", features: [] },
      polygons: {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            properties: { id: featureId, label, group },
            geometry: { type, coordinates: g.coordinates },
          },
        ],
      },
    }
  }

  return {
    points: { type: "FeatureCollection", features: [] },
    polygons: { type: "FeatureCollection", features: [] },
  }
}

export { geometryToFeatureCollections }

export interface LocationGeographySectionProps {
  canonicalId: string
  stylebookSlug: string
  geometry: Record<string, unknown> | null
  canEdit: boolean
  onGeometrySaved: () => void | Promise<void>
}

export default function LocationGeographySection({
  canonicalId,
  stylebookSlug,
  geometry,
  canEdit,
  onGeometrySaved,
}: LocationGeographySectionProps) {
  const { showError, showConfirm } = useAppMessage()
  const [geometryEditing, setGeometryEditing] = useState(false)
  const [geometryDraft, setGeometryDraft] = useState<Record<string, unknown> | null>(geometry)
  const [geometrySaving, setGeometrySaving] = useState(false)
  const [geometryAddMode, setGeometryAddMode] = useState<"point" | "rectangle" | null>(null)
  const [rectanglePreview, setRectanglePreview] = useState<{
    southWest: { lat: number; lng: number }
    northEast: { lat: number; lng: number }
  } | null>(null)

  useEffect(() => {
    if (!geometryEditing) {
      setGeometryDraft(geometry)
    }
  }, [geometry, geometryEditing])

  const saveGeometry = async () => {
    setGeometrySaving(true)
    try {
      await updateCanonicalLocationGeometry(canonicalId, stylebookSlug, geometryDraft)
      setGeometryEditing(false)
      setGeometryAddMode(null)
      setRectanglePreview(null)
      await onGeometrySaved()
    } catch (e) {
      console.error(e)
      const msg =
        e instanceof Error ? e.message : typeof e === "string" ? e : "Save geometry failed"
      showError(msg)
    } finally {
      setGeometrySaving(false)
    }
  }

  const geometrySource = geometryEditing ? geometryDraft : geometry
  const geometryDraftIsMultiPolygon = geometryEditing && isMultiPolygonGeometry(geometryDraft)
  const allowGeometryMapEditing = canEdit && geometryEditing && !geometryDraftIsMultiPolygon

  const leafletCollections = useMemo(() => {
    const base = geometryToFeatureCollections(geometrySource, {
      featureId: "canonical",
      label: "Canonical",
      group: "canonical",
    })

    const stripCanonicalPolygon = (polygons: unknown) => {
      const fc = polygons as {
        type?: string
        features?: Array<{ properties?: { id?: string } }>
      }
      if (!fc || fc.type !== "FeatureCollection" || !Array.isArray(fc.features)) return fc
      return {
        ...fc,
        features: fc.features.filter((f) => f?.properties?.id !== "canonical"),
      }
    }

    const hideCanonicalPolygon =
      geometryEditing &&
      (geometryAddMode === "rectangle" ||
        rectanglePreview != null ||
        axisAlignedRectangleDraft(geometryDraft))

    return {
      points: base.points,
      polygons: hideCanonicalPolygon ? stripCanonicalPolygon(base.polygons) : base.polygons,
    }
  }, [geometryAddMode, geometryDraft, geometryEditing, geometrySource, rectanglePreview])

  const leafletInitialCenter = useMemo((): [number, number] | null => {
    const g = (geometryEditing ? geometryDraft : geometry) as Record<string, unknown> | null
    if (!g) return null
    if (isPointGeometry(g)) {
      const c = g.coordinates
      return [c[1], c[0]]
    }
    if (isPolygonGeometry(g)) {
      const b = boundsFromPolygonGeometry(g)
      if (!b) return null
      const lat = (b.south + b.north) / 2
      const lng = (b.west + b.east) / 2
      return [lat, lng]
    }
    if (isMultiPolygonGeometry(g)) {
      const coords = (g as { coordinates?: number[][][][] }).coordinates?.[0]?.[0]?.[0]
      if (
        Array.isArray(coords) &&
        coords.length >= 2 &&
        typeof coords[0] === "number" &&
        typeof coords[1] === "number"
      ) {
        return [coords[1], coords[0]]
      }
    }
    return null
  }, [geometry, geometryDraft, geometryEditing])

  const cancelGeometryEdit = useCallback(() => {
    setGeometryDraft(geometry)
    setGeometryAddMode(null)
    setRectanglePreview(null)
    setGeometryEditing(false)
  }, [geometry])

  return (
    <Card
      className={cn(
        "relative z-0 isolate",
        geometryEditing && "border-2 border-foreground/80 bg-white shadow-sm transition-colors",
      )}
    >
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2">
            <span>Geography</span>
            {geometryEditing ? (
              <Badge variant="secondary" className="font-normal">
                Editing draft
              </Badge>
            ) : null}
          </CardTitle>
          <CardDescription>
            {geometryEditing
              ? geometryAddMode === "point"
                ? "Click the map to place a point."
                : geometryAddMode === "rectangle"
                  ? "Hold Shift and drag on the map to draw an axis-aligned rectangle."
                  : "Edit canonical geometry (draft) and save or cancel."
              : "View canonical geometry."}
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          {geometryEditing ? (
            <>
              <Button variant="outline" onClick={cancelGeometryEdit} disabled={geometrySaving}>
                Cancel
              </Button>
              <Button onClick={() => void saveGeometry()} disabled={geometrySaving}>
                {geometrySaving ? "Saving…" : "Save"}
              </Button>
            </>
          ) : (
            <Button
              variant="outline"
              onClick={() => {
                setGeometryDraft(geometry)
                setGeometryAddMode(null)
                setRectanglePreview(null)
                setGeometryEditing(true)
              }}
              disabled={!canEdit}
            >
              Edit geography
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {geometryEditing && isMultiPolygonGeometry(geometryDraft) ? (
          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription>
              Editing is disabled for MultiPolygon geometries. These complex geometries contain
              multiple polygons and require specialized editing tools. You can delete the geometry,
              then add a point or rectangle replacement.
            </AlertDescription>
          </Alert>
        ) : null}

        {geometryEditing ? (
          <div className="flex flex-wrap gap-2">
            {!geometryDraft ? (
              <>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={geometryAddMode === "point" || geometrySaving}
                  onClick={() => {
                    setGeometryAddMode("point")
                    setRectanglePreview(null)
                  }}
                >
                  <MousePointer className="h-4 w-4 mr-2" />
                  Add point
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={geometryAddMode === "rectangle" || geometrySaving}
                  onClick={() => {
                    setGeometryAddMode("rectangle")
                    setRectanglePreview(null)
                  }}
                >
                  <Square className="h-4 w-4 mr-2" />
                  Add rectangle
                </Button>
              </>
            ) : (
              <Button
                type="button"
                variant="destructive"
                size="sm"
                disabled={geometrySaving}
                onClick={() => {
                  void (async () => {
                    const ok = await showConfirm("Delete this geometry?", {
                      title: "Delete geometry",
                      confirmLabel: "Delete",
                      destructive: true,
                    })
                    if (!ok) return
                    setGeometryDraft(null)
                    setGeometryAddMode(null)
                    setRectanglePreview(null)
                  })()
                }}
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Delete geometry
              </Button>
            )}
          </div>
        ) : null}

        <div
          className={cn(
            "rounded-md overflow-hidden",
            geometryEditing && "bg-white ring-1 ring-foreground/25 border border-foreground/30",
          )}
        >
          <GeometryEditLeafletMap
            points={leafletCollections.points as Parameters<typeof GeometryEditLeafletMap>[0]["points"]}
            polygons={
              leafletCollections.polygons as Parameters<typeof GeometryEditLeafletMap>[0]["polygons"]
            }
            geometryEditing={allowGeometryMapEditing}
            geometryDraft={geometryDraft}
            onGeometryDraftChange={setGeometryDraft}
            geometryAddMode={geometryAddMode}
            onGeometryAddModeChange={setGeometryAddMode}
            editPointFeatureId="canonical"
            initialCenter={leafletInitialCenter}
            rectanglePreview={rectanglePreview}
            onRectanglePreviewChange={setRectanglePreview}
            showPopups={false}
          />
        </div>
        {geometryEditing && !geometryDraftIsMultiPolygon ? (
          <SimpleGeoJsonGeometry value={geometryDraft} onChange={setGeometryDraft} />
        ) : null}
      </CardContent>
    </Card>
  )
}
