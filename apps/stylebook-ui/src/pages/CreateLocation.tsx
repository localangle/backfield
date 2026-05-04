import { useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAppMessage } from "@/components/AppMessageProvider"
import { useProjectCatalogScope } from "@/lib/catalogNavigation"
import { createLocation } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import SimpleGeoJsonGeometry from "@/components/SimpleGeoJsonGeometry"
import { fetchPlaceExtractLocationTypes } from "@/lib/stylebook-api/taxonomy"
import {
  PLACE_EXTRACT_LOCATION_TYPES,
  placeExtractTypeLabel,
  sortReviewQueueTypeFilterOptions,
} from "@/lib/place-extract-type-label"
import { slugifyLocationTypeLabel } from "@/lib/import/geojsonImport"
import { LeafletMap } from "@backfield/ui/LeafletMap"
import {
  boundsFromPolygonGeometry,
  isAxisAlignedRectanglePolygon,
  polygonFromAxisAlignedBounds,
} from "@backfield/ui/axisAlignedRectangle"
import { cn } from "@/lib/utils"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Info, Loader2, MousePointer, Square, Trash2 } from "lucide-react"

/** Continental US when adding the first geometry from an empty draft (matches LeafletMap defaults). */
const ADD_GEOMETRY_MAP_CENTER: [number, number] = [39.8283, -98.5795]
/** Match @backfield/ui LeafletMap continental US default framing. */
const ADD_GEOMETRY_MAP_ZOOM = 3

/** Radix Select value when no type is chosen */
const CREATE_LOCATION_TYPE_NONE = "__none__"
/** Location type: Custom + — enter a label → slug (not from the taxonomy list). */
const CREATE_LOCATION_TYPE_CUSTOM = "__custom__"

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
): { points: unknown; polygons: unknown } {
  if (!geometry || typeof geometry !== "object") {
    return {
      points: { type: "FeatureCollection", features: [] },
      polygons: { type: "FeatureCollection", features: [] },
    }
  }

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
            properties: { id: "canonical", label: "Canonical", group: "canonical" },
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
            properties: { id: "canonical", label: "Canonical", group: "canonical" },
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

export default function CreateLocation() {
  const { showMessage, showError, showConfirm } = useAppMessage()
  const navigate = useNavigate()
  const { scopeSuffix } = useProjectCatalogScope()
  const [projectSlug, setProjectSlug] = useState("")
  const [name, setName] = useState("")
  const [locationType, setLocationType] = useState("")
  const [locationTypeSelect, setLocationTypeSelect] = useState<string>(CREATE_LOCATION_TYPE_NONE)
  const [customLocationTypeLabel, setCustomLocationTypeLabel] = useState("")
  const [placeExtractTypesList, setPlaceExtractTypesList] = useState<string[]>(() => [
    ...PLACE_EXTRACT_LOCATION_TYPES,
  ])
  const [formattedAddress, setFormattedAddress] = useState("")
  const [geometry, setGeometry] = useState<Record<string, unknown> | null>(null)
  const [geometryEditing, setGeometryEditing] = useState(true)
  const [geometryDraft, setGeometryDraft] = useState<Record<string, unknown> | null>(null)
  const [geometryAddMode, setGeometryAddMode] = useState<"point" | "rectangle" | null>(null)
  const [rectanglePreview, setRectanglePreview] = useState<{
    southWest: { lat: number; lng: number }
    northEast: { lat: number; lng: number }
  } | null>(null)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    const slug = new URLSearchParams(window.location.search).get("project") || ""
    setProjectSlug(slug)
  }, [])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await fetchPlaceExtractLocationTypes()
        if (!cancelled && Array.isArray(res.types) && res.types.length > 0) {
          setPlaceExtractTypesList(res.types)
        }
      } catch {
        // Keep bundled ``PLACE_EXTRACT_LOCATION_TYPES`` fallback.
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const sortedLocationTypes = useMemo(
    () => sortReviewQueueTypeFilterOptions([...placeExtractTypesList]),
    [placeExtractTypesList],
  )

  const storedLocationTypeSlug =
    locationTypeSelect === CREATE_LOCATION_TYPE_CUSTOM
      ? slugifyLocationTypeLabel(customLocationTypeLabel)
      : locationType.trim()

  const handleLocationTypeSelect = (value: string) => {
    setLocationTypeSelect(value)

    if (value === CREATE_LOCATION_TYPE_NONE) {
      setCustomLocationTypeLabel("")
      setLocationType("")
      return
    }

    if (value === CREATE_LOCATION_TYPE_CUSTOM) {
      setCustomLocationTypeLabel("")
      setLocationType("")
      return
    }

    // Preset slug from taxonomy.
    setCustomLocationTypeLabel("")
    setLocationType(value)
  }

  const handleSubmit = async () => {
    if (!name.trim()) {
      showMessage("Please enter a location name", { title: "Name required" })
      return
    }
    try {
      setCreating(true)
      const geometryToCreate = geometryEditing ? geometryDraft : geometry
      const location = await createLocation(projectSlug, {
        name: name.trim(),
        location_type: storedLocationTypeSlug || undefined,
        formatted_address: formattedAddress.trim() || undefined,
        geometry_json: geometryToCreate ?? undefined,
        status: "active",
      })
      navigate(`/locations/canonical/${location.id}${scopeSuffix}`)
    } catch (error) {
      console.error("Failed to create location:", error)
      showError(
        `Failed to create location: ${error instanceof Error ? error.message : "Unknown error"}`,
      )
    } finally {
      setCreating(false)
    }
  }

  const handleCancel = () => {
    navigate(`/locations/canonical${scopeSuffix}`)
  }

  const geometrySource = geometryEditing ? geometryDraft : geometry

  const leafletCollections = useMemo(() => {
    const base = geometryToFeatureCollections(geometrySource as any)

    const stripCanonicalPolygon = (polygons: any) => {
      const fc = polygons as any
      if (!fc || typeof fc !== "object" || fc.type !== "FeatureCollection" || !Array.isArray(fc.features)) return fc
      return {
        ...fc,
        features: fc.features.filter((f: any) => {
          const id = f?.properties?.id
          return id !== "canonical"
        }),
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
      const b = boundsFromPolygonGeometry(g as any)
      if (!b) return null
      const lat = (b.south + b.north) / 2
      const lng = (b.west + b.east) / 2
      return [lat, lng]
    }
    if (isMultiPolygonGeometry(g)) {
      const coords = (g as any).coordinates?.[0]?.[0]?.[0]
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

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Create Location</h1>
      </div>

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-6">
          <Card>
            <CardHeader>
              <CardTitle>Location Details</CardTitle>
              <CardDescription>Enter the basic information for this location</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="name">Name *</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g., Chicago, IL"
                />
              </div>
              <div>
                <Label htmlFor="locationType">Location Type (optional)</Label>
                <div className="space-y-2">
                  <Select value={locationTypeSelect} onValueChange={handleLocationTypeSelect}>
                    <SelectTrigger id="locationType" className="h-10 w-full">
                      <SelectValue placeholder="Select location type…" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={CREATE_LOCATION_TYPE_NONE}>None</SelectItem>
                      {sortedLocationTypes.map((slug) => (
                        <SelectItem key={slug} value={slug}>
                          {placeExtractTypeLabel(slug)}
                        </SelectItem>
                      ))}
                      <SelectItem value={CREATE_LOCATION_TYPE_CUSTOM}>Custom +</SelectItem>
                    </SelectContent>
                  </Select>

                  {locationTypeSelect === CREATE_LOCATION_TYPE_CUSTOM ? (
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:items-start">
                      <div className="min-w-0 space-y-1.5">
                        <span className="text-xs text-muted-foreground">Label</span>
                        <Input
                          value={customLocationTypeLabel}
                          placeholder="e.g. Congressional District"
                          className="h-10 font-normal"
                          onChange={(e) => {
                            const next = e.target.value
                            setCustomLocationTypeLabel(next)
                            setLocationType(slugifyLocationTypeLabel(next))
                          }}
                        />
                      </div>
                      <div className="min-w-0 space-y-1.5">
                        <span className="text-xs text-muted-foreground">Stored as (slug)</span>
                        <Input
                          readOnly
                          tabIndex={-1}
                          value={storedLocationTypeSlug}
                          placeholder="custom_type"
                          className="h-10 font-mono text-sm bg-muted/40"
                        />
                      </div>
                    </div>
                  ) : locationTypeSelect !== CREATE_LOCATION_TYPE_NONE ? (
                    <div className="space-y-1.5">
                      <span className="text-xs text-muted-foreground">Stored as (slug)</span>
                      <Input
                        readOnly
                        tabIndex={-1}
                        value={storedLocationTypeSlug}
                        className="h-10 font-mono text-sm bg-muted/40"
                      />
                    </div>
                  ) : null}
                </div>
              </div>
              <div>
                <Label htmlFor="formattedAddress">Formatted Address</Label>
                <Input
                  id="formattedAddress"
                  value={formattedAddress}
                  onChange={(e) => setFormattedAddress(e.target.value)}
                  placeholder="e.g., Chicago, IL, United States"
                />
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="col-span-6">
          <Card>
            <CardHeader>
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
                      : "Draw or edit geometry and apply it to the new canonical."
                  : "View geometry."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {!geometryEditing && isMultiPolygonGeometry(geometry) ? (
                <Alert>
                  <Info className="h-4 w-4" />
                  <AlertDescription>
                    Editing is disabled for MultiPolygon geometries. These complex geometries contain multiple polygons and
                    require specialized editing tools.
                  </AlertDescription>
                </Alert>
              ) : null}

              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap gap-2">
                  {geometryEditing ? (
                    <>
                      {!geometryDraft ? (
                        <>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={geometryAddMode === "point"}
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
                            disabled={geometryAddMode === "rectangle"}
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
                    </>
                  ) : null}
                </div>

                <div className="flex items-center gap-2">
                  {geometryEditing ? (
                    <>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setGeometryDraft(geometry)
                          setGeometryAddMode(null)
                          setRectanglePreview(null)
                          setGeometryEditing(false)
                        }}
                      >
                        Cancel
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => {
                          setGeometry(geometryDraft)
                          setGeometryAddMode(null)
                          setRectanglePreview(null)
                          setGeometryEditing(false)
                        }}
                      >
                        Apply
                      </Button>
                    </>
                  ) : (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setGeometryDraft(geometry)
                        setGeometryAddMode(null)
                        setRectanglePreview(null)
                        setGeometryEditing(true)
                      }}
                      disabled={isMultiPolygonGeometry(geometry)}
                    >
                      Edit geography
                    </Button>
                  )}
                </div>
              </div>

              <div
                className={cn(
                  "rounded-md overflow-hidden",
                  geometryEditing && "bg-white ring-1 ring-foreground/25 border border-foreground/30",
                )}
              >
                <LeafletMap
                  points={leafletCollections.points as any}
                  polygons={leafletCollections.polygons as any}
                  geocoder={geometryEditing}
                  showPopups={false}
                  fitToData={!geometryEditing}
                  initialCenter={
                    geometryEditing &&
                    !geometryDraft &&
                    (geometryAddMode === "point" || geometryAddMode === "rectangle")
                      ? ADD_GEOMETRY_MAP_CENTER
                      : leafletInitialCenter
                  }
                  initialZoom={
                    geometryEditing &&
                    !geometryDraft &&
                    (geometryAddMode === "point" || geometryAddMode === "rectangle")
                      ? ADD_GEOMETRY_MAP_ZOOM
                      : null
                  }
                  interactiveWhenEmpty={geometryEditing && geometryAddMode === "point" && !geometryDraft}
                  tileUrl={
                    geometryEditing
                      ? "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
                      : undefined
                  }
                  tileAttribution={
                    geometryEditing
                      ? '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
                      : undefined
                  }
                  onMapClick={
                    geometryEditing &&
                    geometryAddMode === "point" &&
                    (!geometryDraft || isPointGeometry(geometryDraft))
                      ? ({ latlng }) => {
                          setGeometryDraft({ type: "Point", coordinates: [latlng.lng, latlng.lat] })
                          setGeometryAddMode(null)
                        }
                      : undefined
                  }
                  editablePoint={
                    geometryEditing &&
                    isPointGeometry(geometryDraft) &&
                    geometryAddMode !== "rectangle"
                      ? {
                          featureId: "canonical",
                          onChange: ({ lng, lat }) =>
                            setGeometryDraft({ type: "Point", coordinates: [lng, lat] }),
                        }
                      : null
                  }
                  rectanglePreview={geometryEditing ? rectanglePreview : null}
                  editableRectangle={
                    geometryEditing &&
                    axisAlignedRectangleDraft(geometryDraft) &&
                    geometryAddMode !== "rectangle" &&
                    boundsFromPolygonGeometry(geometryDraft as any)
                      ? (() => {
                          const b = boundsFromPolygonGeometry(geometryDraft as any)!
                          return {
                            southWest: { lat: b.south, lng: b.west },
                            northEast: { lat: b.north, lng: b.east },
                            onChange: (next) => {
                              setGeometryDraft(
                                polygonFromAxisAlignedBounds({
                                  west: next.southWest.lng,
                                  south: next.southWest.lat,
                                  east: next.northEast.lng,
                                  north: next.northEast.lat,
                                }) as any,
                              )
                            },
                          }
                        })()
                      : null
                  }
                  rectangleDraw={
                    geometryEditing && geometryAddMode === "rectangle"
                      ? {
                          enabled: true,
                          onPreview: setRectanglePreview,
                          onCommit: (bounds) => {
                            setGeometryDraft(
                              polygonFromAxisAlignedBounds({
                                west: bounds.southWest.lng,
                                south: bounds.southWest.lat,
                                east: bounds.northEast.lng,
                                north: bounds.northEast.lat,
                              }) as any,
                            )
                            setRectanglePreview(null)
                            setGeometryAddMode(null)
                          },
                        }
                      : null
                  }
                />
              </div>

              {geometryEditing ? (
                <SimpleGeoJsonGeometry value={geometryDraft} onChange={setGeometryDraft} />
              ) : null}
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="mt-6 flex justify-end gap-2">
        <Button variant="outline" onClick={handleCancel} disabled={creating}>
          Cancel
        </Button>
        <Button onClick={handleSubmit} disabled={creating || !name.trim()}>
          {creating ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Creating...
            </>
          ) : (
            "Create Location"
          )}
        </Button>
      </div>
    </div>
  )
}
