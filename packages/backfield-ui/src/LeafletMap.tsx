import { useEffect, useMemo, useRef, useState } from "react"
import type { ReactNode } from "react"
import * as L from "leaflet"
import { CircleMarker, MapContainer, Marker, Polygon, Popup, TileLayer, useMap, useMapEvents } from "react-leaflet"
import "leaflet/dist/leaflet.css"

type LngLat = [number, number] // [lng, lat]
type LatLng = [number, number] // [lat, lng]

type FeatureId = string

type GeoJsonGeometry =
  | { type: "Point"; coordinates: [number, number] }
  | { type: "Polygon"; coordinates: [number, number][][] }
  | { type: "MultiPolygon"; coordinates: [number, number][][][] }

type GeoJsonFeature<G extends GeoJsonGeometry = GeoJsonGeometry> = {
  type: "Feature"
  id?: FeatureId
  properties?: Record<string, unknown> & { id?: FeatureId }
  geometry: G
}

type GeoJsonFeatureCollection = {
  type: "FeatureCollection"
  features: GeoJsonFeature[]
}

export type LeafletMapFeatureClick = {
  featureId: string | null
  feature: GeoJsonFeature
  latlng: { lat: number; lng: number }
}

export type LeafletMapProps = {
  points?: GeoJsonFeatureCollection | null
  polygons?: GeoJsonFeatureCollection | null
  height?: number
  emptyState?: ReactNode
  onFeatureClick?: (event: LeafletMapFeatureClick) => void
  fitToData?: boolean
  showPopups?: boolean
  onMapClick?: (event: { latlng: { lat: number; lng: number } }) => void
  editablePoint?: {
    featureId: string
    onChange: (next: { lng: number; lat: number }) => void
  } | null
  tileUrl?: string
  tileAttribution?: string
}

const DEFAULT_CENTER: LatLng = [39.8283, -98.5795] // continental US
const DEFAULT_ZOOM = 3

function isFiniteNumber(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v)
}

function normalizeFeatureCollection(input: unknown): GeoJsonFeatureCollection {
  if (!input || typeof input !== "object") {
    return { type: "FeatureCollection", features: [] }
  }
  const obj = input as Record<string, unknown>
  if (obj.type !== "FeatureCollection" || !Array.isArray(obj.features)) {
    return { type: "FeatureCollection", features: [] }
  }

  const features: GeoJsonFeature[] = []
  for (const raw of obj.features) {
    if (!raw || typeof raw !== "object") continue
    const f = raw as Record<string, unknown>
    if (f.type !== "Feature") continue
    const geometry = f.geometry as any
    if (!geometry || typeof geometry !== "object") continue
    if (geometry.type !== "Point" && geometry.type !== "Polygon" && geometry.type !== "MultiPolygon") continue
    // Keep validation light here; rendering layer should be robust against odd rings.
    features.push(raw as GeoJsonFeature)
  }

  return { type: "FeatureCollection", features }
}

function extractLatLngBounds(collections: GeoJsonFeatureCollection[]): [LatLng, LatLng] | null {
  let minLng = Infinity
  let minLat = Infinity
  let maxLng = -Infinity
  let maxLat = -Infinity
  let has = false

  const extend = (lng: unknown, lat: unknown) => {
    if (!isFiniteNumber(lng) || !isFiniteNumber(lat)) return
    minLng = Math.min(minLng, lng)
    minLat = Math.min(minLat, lat)
    maxLng = Math.max(maxLng, lng)
    maxLat = Math.max(maxLat, lat)
    has = true
  }

  for (const fc of collections) {
    for (const feature of fc.features) {
      const g = feature.geometry as any
      if (!g) continue
      if (g.type === "Point") {
        const c = g.coordinates
        if (Array.isArray(c) && c.length >= 2) extend(c[0], c[1])
        continue
      }
      if (g.type === "Polygon") {
        const rings = g.coordinates
        if (!Array.isArray(rings)) continue
        for (const ring of rings) {
          if (!Array.isArray(ring)) continue
          for (const coord of ring) {
            if (Array.isArray(coord) && coord.length >= 2) extend(coord[0], coord[1])
          }
        }
        continue
      }
      if (g.type === "MultiPolygon") {
        const polys = g.coordinates
        if (!Array.isArray(polys)) continue
        for (const poly of polys) {
          if (!Array.isArray(poly)) continue
          for (const ring of poly) {
            if (!Array.isArray(ring)) continue
            for (const coord of ring) {
              if (Array.isArray(coord) && coord.length >= 2) extend(coord[0], coord[1])
            }
          }
        }
      }
    }
  }

  if (!has) return null
  return [
    [minLat, minLng],
    [maxLat, maxLng],
  ]
}

function FitToData({ bounds }: { bounds: [LatLng, LatLng] | null }) {
  const map = useMap()
  useEffect(() => {
    if (!bounds) return
    try {
      map.fitBounds(bounds as any, { padding: [32, 32], maxZoom: 13 })
    } catch {
      // Defensive: never let fit bounds crash the page.
    }
  }, [map, bounds])
  return null
}

function featureIdOf(feature: GeoJsonFeature): string | null {
  const fromProps = feature.properties?.id
  if (typeof fromProps === "string" && fromProps.trim()) return fromProps
  if (typeof feature.id === "string" && feature.id.trim()) return feature.id
  return null
}

function featureLabelOf(feature: GeoJsonFeature): string {
  const props = (feature.properties ?? {}) as Record<string, unknown>
  const label = typeof props.label === "string" ? props.label.trim() : ""
  if (label) return label
  const id = featureIdOf(feature)
  return id ?? "Feature"
}

function featureRoleOf(feature: GeoJsonFeature): string | null {
  const props = (feature.properties ?? {}) as Record<string, unknown>
  const role = typeof props.group === "string" ? props.group.trim() : ""
  return role || null
}

function featureDescriptionOf(feature: GeoJsonFeature): string | null {
  const props = (feature.properties ?? {}) as Record<string, unknown>
  const desc = typeof props.description === "string" ? props.description.trim() : ""
  return desc || null
}

export function LeafletMap({
  points,
  polygons,
  height = 420,
  emptyState,
  onFeatureClick,
  fitToData = true,
  showPopups = true,
  onMapClick,
  editablePoint = null,
  tileUrl = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  tileAttribution = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}: LeafletMapProps) {
  const [error, setError] = useState<string | null>(null)
  const clickHandlerRef = useRef(onFeatureClick)
  useEffect(() => {
    clickHandlerRef.current = onFeatureClick
  }, [onFeatureClick])

  const [popup, setPopup] = useState<{
    latlng: { lat: number; lng: number }
    title: string
    role: string | null
    description: string | null
    feature: GeoJsonFeature
  } | null>(null)

  useEffect(() => {
    if (!showPopups) setPopup(null)
  }, [showPopups])

  const normalizedPoints = useMemo(() => normalizeFeatureCollection(points), [points])
  const normalizedPolygons = useMemo(() => normalizeFeatureCollection(polygons), [polygons])

  const hasAny = normalizedPoints.features.length > 0 || normalizedPolygons.features.length > 0

  const bounds = useMemo(
    () => (fitToData ? extractLatLngBounds([normalizedPoints, normalizedPolygons]) : null),
    [fitToData, normalizedPoints, normalizedPolygons],
  )

  useEffect(() => {
    // If callers pass bad data, prefer a soft error state over crashing during render.
    // (normalizeFeatureCollection already strips most invalid shapes.)
    setError(null)
  }, [points, polygons])

  if (!hasAny) {
    return (
      <div style={{ height }} className="rounded-md border border-dashed border-muted flex items-center justify-center">
        {emptyState ?? <div className="text-sm text-muted-foreground">No geographic features.</div>}
      </div>
    )
  }

  const polygonPaths = normalizedPolygons.features
    .map((f) => {
      const g = f.geometry
      if (g.type === "Polygon") return [f] as const
      if (g.type === "MultiPolygon") {
        const polys = g.coordinates
        if (!Array.isArray(polys)) return [] as const
        return polys.map((coords) => ({
          ...f,
          geometry: { type: "Polygon" as const, coordinates: coords },
        }))
      }
      return [] as const
    })
    .flat()

  const editablePointFeature = useMemo(() => {
    if (!editablePoint) return null
    return normalizedPoints.features.find((f) => featureIdOf(f) === editablePoint.featureId) ?? null
  }, [editablePoint, normalizedPoints.features])

  const editablePointCenter = useMemo((): [number, number] | null => {
    if (!editablePointFeature) return null
    const c = editablePointFeature.geometry.coordinates
    if (!Array.isArray(c) || c.length < 2) return null
    const lng = c[0]
    const lat = c[1]
    if (!isFiniteNumber(lng) || !isFiniteNumber(lat)) return null
    return [lat, lng]
  }, [editablePointFeature])

  const editablePointIcon = useMemo(() => {
    if (!editablePointCenter) return null
    return L.divIcon({
      className: "",
      html: `<div style="
        width: 14px;
        height: 14px;
        border-radius: 9999px;
        background: #ef4444;
        border: 2px solid #ffffff;
        box-shadow: 0 1px 2px rgba(0,0,0,0.25);
      "></div>`,
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    })
  }, [editablePointCenter])

  function MapClickHandler() {
    useMapEvents({
      click: (e) => {
        if (!onMapClick) return
        const latlng = e?.latlng
        if (!latlng || !isFiniteNumber(latlng.lat) || !isFiniteNumber(latlng.lng)) return
        onMapClick({ latlng: { lat: latlng.lat, lng: latlng.lng } })
      },
    })
    return null
  }

  return (
    <div className="rounded-md overflow-hidden border border-border" style={{ height }}>
      {error ? <div className="p-3 text-sm text-destructive">{error}</div> : null}
      <MapContainer center={DEFAULT_CENTER as any} zoom={DEFAULT_ZOOM} style={{ height: "100%", width: "100%" }}>
        <MapClickHandler />
        <TileLayer attribution={tileAttribution} url={tileUrl} />
        {fitToData ? <FitToData bounds={bounds} /> : null}
        {polygonPaths.map((feature, idx) => {
          const coords = feature.geometry.coordinates?.[0]
          if (!Array.isArray(coords) || coords.length === 0) return null
          const positions = coords
            .filter((c) => Array.isArray(c) && c.length >= 2 && isFiniteNumber(c[0]) && isFiniteNumber(c[1]))
            .map((c) => [c[1], c[0]] as [number, number])
          if (positions.length === 0) return null
          return (
            <Polygon
              key={`${featureIdOf(feature) ?? "poly"}-${idx}`}
              positions={positions}
              pathOptions={{ color: "#1d4ed8", weight: 2, fillColor: "#3b82f6", fillOpacity: 0.2 }}
              eventHandlers={{
                click: (e: any) => {
                  const latlng = e?.latlng
                  if (!latlng || !isFiniteNumber(latlng.lat) || !isFiniteNumber(latlng.lng)) return
                  if (showPopups) {
                    setPopup({
                      latlng: { lat: latlng.lat, lng: latlng.lng },
                      title: featureLabelOf(feature),
                      role: featureRoleOf(feature),
                      description: featureDescriptionOf(feature),
                      feature,
                    })
                  }
                  clickHandlerRef.current?.({ featureId: featureIdOf(feature), feature, latlng })
                },
              }}
            />
          )
        })}

        {normalizedPoints.features.map((feature, idx) => {
          if (editablePoint && featureIdOf(feature) === editablePoint.featureId) return null
          const c = feature.geometry.coordinates
          if (!Array.isArray(c) || c.length < 2) return null
          const lng = c[0]
          const lat = c[1]
          if (!isFiniteNumber(lng) || !isFiniteNumber(lat)) return null
          return (
            <CircleMarker
              key={`${featureIdOf(feature) ?? "pt"}-${idx}`}
              center={[lat, lng]}
              radius={6}
              pathOptions={{ color: "#ffffff", weight: 2, fillColor: "#ef4444", fillOpacity: 0.9 }}
              eventHandlers={{
                click: (e: any) => {
                  const latlng = e?.latlng
                  if (!latlng || !isFiniteNumber(latlng.lat) || !isFiniteNumber(latlng.lng)) return
                  if (showPopups) {
                    setPopup({
                      latlng: { lat: latlng.lat, lng: latlng.lng },
                      title: featureLabelOf(feature),
                      role: featureRoleOf(feature),
                      description: featureDescriptionOf(feature),
                      feature,
                    })
                  }
                  clickHandlerRef.current?.({ featureId: featureIdOf(feature), feature, latlng })
                },
              }}
            />
          )
        })}

        {editablePoint && editablePointCenter && editablePointIcon ? (
          <Marker
            position={editablePointCenter}
            draggable
            icon={editablePointIcon as any}
            eventHandlers={{
              dragend: (e: any) => {
                const latlng = e?.target?.getLatLng?.()
                if (!latlng || !isFiniteNumber(latlng.lat) || !isFiniteNumber(latlng.lng)) return
                editablePoint.onChange({ lng: latlng.lng, lat: latlng.lat })
              },
            }}
          />
        ) : null}

        {showPopups && popup ? (
          <Popup
            position={[popup.latlng.lat, popup.latlng.lng]}
            closeButton
            closeOnClick
            autoPan
            eventHandlers={{
              remove: () => setPopup(null),
            }}
          >
            <div className="text-sm">
              <div className="font-medium">{popup.title}</div>
              {popup.role ? (
                <div className="mt-0.5 text-xs text-muted-foreground">
                  Role: <span className="capitalize">{popup.role}</span>
                </div>
              ) : null}
              {popup.description ? (
                <div className="mt-1 text-xs text-muted-foreground">{popup.description}</div>
              ) : null}
            </div>
          </Popup>
        ) : null}
      </MapContainer>
    </div>
  )
}

