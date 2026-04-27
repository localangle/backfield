import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { MutableRefObject, ReactNode } from "react"
import * as L from "leaflet"
import { CircleMarker, MapContainer, Marker, Polygon, Popup, Rectangle, TileLayer, useMap, useMapEvents } from "react-leaflet"
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

export type AxisAlignedRectangleLngLat = {
  southWest: { lat: number; lng: number }
  northEast: { lat: number; lng: number }
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
  /** When set, used as the map center if the map renders without fit-to-data bounds. */
  initialCenter?: LatLng | null
  initialZoom?: number | null
  showPopups?: boolean
  onMapClick?: (event: { latlng: { lat: number; lng: number } }) => void
  editablePoint?: {
    featureId: string
    onChange: (next: { lng: number; lat: number }) => void
  } | null
  rectanglePreview?: AxisAlignedRectangleLngLat | null
  editableRectangle?: AxisAlignedRectangleLngLat & {
    onChange: (next: AxisAlignedRectangleLngLat) => void
  } | null
  rectangleDraw?: {
    enabled: boolean
    onPreview: (preview: AxisAlignedRectangleLngLat | null) => void
    onCommit: (bounds: AxisAlignedRectangleLngLat) => void
  } | null
  /**
   * When true, render the interactive map even if there are no points/polygons/previews yet
   * (e.g. click-to-add point before the first geometry exists).
   */
  interactiveWhenEmpty?: boolean
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

function extractLatLngBounds(collections: GeoJsonFeatureCollection[], extraBounds?: L.LatLngBounds | null): [LatLng, LatLng] | null {
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

  if (extraBounds) {
    const sw = extraBounds.getSouthWest()
    const ne = extraBounds.getNorthEast()
    if (isFiniteNumber(sw.lng) && isFiniteNumber(sw.lat) && isFiniteNumber(ne.lng) && isFiniteNumber(ne.lat)) {
      extend(sw.lng, sw.lat)
      extend(ne.lng, ne.lat)
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

const RECT_EDIT_DEBUG =
  typeof import.meta !== "undefined" &&
  Boolean((import.meta as ImportMeta & { env?: { DEV?: boolean } }).env?.DEV)

function rectEditDebug(...args: unknown[]) {
  if (!RECT_EDIT_DEBUG) return
  // eslint-disable-next-line no-console -- dev-only diagnostics for rectangle edit / drag
  console.debug("[LeafletMap.rect]", ...args)
}

type RectangleDrawingActiveRef = MutableRefObject<boolean>

type MapClickHandlerProps = {
  onMapClick?: LeafletMapProps["onMapClick"]
  rectangleDrawingRef: RectangleDrawingActiveRef
}

function MapClickHandler({ onMapClick, rectangleDrawingRef }: MapClickHandlerProps) {
  useMapEvents({
    click: (e) => {
      if (!onMapClick) return
      if (rectangleDrawingRef.current) return
      const latlng = e?.latlng
      if (!latlng || !isFiniteNumber(latlng.lat) || !isFiniteNumber(latlng.lng)) return
      onMapClick({ latlng: { lat: latlng.lat, lng: latlng.lng } })
    },
  })
  return null
}

type RectangleDrawControllerProps = {
  rectangleDrawRef: MutableRefObject<LeafletMapProps["rectangleDraw"]>
  rectangleDrawingRef: RectangleDrawingActiveRef
}

function RectangleDrawController({ rectangleDrawRef, rectangleDrawingRef }: RectangleDrawControllerProps) {
  const map = useMap()

  const drawMoveListenerRef = useRef<(ev: MouseEvent) => void>(() => {})
  const drawUpListenerRef = useRef<(ev: MouseEvent) => void>(() => {})

  const detachDrawListeners = useCallback(() => {
    L.DomEvent.off(document as any, "mousemove", drawMoveListenerRef.current as any)
    L.DomEvent.off(document as any, "mouseup", drawUpListenerRef.current as any)
  }, [])

  const cleanupDragState = useCallback(() => {
    rectangleDrawingRef.current = false
    detachDrawListeners()
    try {
      map.dragging?.enable()
    } catch {
      // ignore
    }
  }, [detachDrawListeners, map, rectangleDrawingRef])

  useMapEvents({
    mousedown: (e: any) => {
      if (!rectangleDrawRef.current?.enabled) return
      const latlng = e?.latlng
      if (!latlng || !isFiniteNumber(latlng.lat) || !isFiniteNumber(latlng.lng)) return

      rectangleDrawingRef.current = true
      const start = { lat: latlng.lat, lng: latlng.lng }

      try {
        map.dragging?.disable()
      } catch {
        // ignore
      }

      drawMoveListenerRef.current = (moveEvent: MouseEvent) => {
        const ll = map.mouseEventToLatLng(moveEvent)
        if (!ll || !isFiniteNumber(ll.lat) || !isFiniteNumber(ll.lng)) return
        const swLat = Math.min(start.lat, ll.lat)
        const neLat = Math.max(start.lat, ll.lat)
        const swLng = Math.min(start.lng, ll.lng)
        const neLng = Math.max(start.lng, ll.lng)
        rectangleDrawRef.current?.onPreview({
          southWest: { lat: swLat, lng: swLng },
          northEast: { lat: neLat, lng: neLng },
        })
      }

      drawUpListenerRef.current = (upEvent: MouseEvent) => {
        detachDrawListeners()

        const ll = map.mouseEventToLatLng(upEvent)
        cleanupDragState()
        rectangleDrawRef.current?.onPreview(null)

        if (!ll || !isFiniteNumber(ll.lat) || !isFiniteNumber(ll.lng)) return

        const swLat = Math.min(start.lat, ll.lat)
        const neLat = Math.max(start.lat, ll.lat)
        const swLng = Math.min(start.lng, ll.lng)
        const neLng = Math.max(start.lng, ll.lng)

        // Ignore tiny accidental clicks
        if (Math.abs(neLat - swLat) < 1e-8 || Math.abs(neLng - swLng) < 1e-8) return

        rectangleDrawRef.current?.onCommit({
          southWest: { lat: swLat, lng: swLng },
          northEast: { lat: neLat, lng: neLng },
        })
      }

      rectangleDrawRef.current?.onPreview({
        southWest: { lat: start.lat, lng: start.lng },
        northEast: { lat: start.lat, lng: start.lng },
      })

      L.DomEvent.on(document as any, "mousemove", drawMoveListenerRef.current as any)
      L.DomEvent.on(document as any, "mouseup", drawUpListenerRef.current as any)
    },
  })

  useEffect(() => {
    return () => {
      cleanupDragState()
      rectangleDrawRef.current?.onPreview(null)
    }
  }, [cleanupDragState, rectangleDrawRef])

  return null
}

type EditableAxisAlignedRectangleProps = {
  leafletBounds: L.LatLngBounds
  onChange: (next: AxisAlignedRectangleLngLat) => void
  rectangleDrawingRef: RectangleDrawingActiveRef
}

function EditableAxisAlignedRectangle({ leafletBounds, onChange, rectangleDrawingRef }: EditableAxisAlignedRectangleProps) {
  const map = useMap()

  useEffect(() => {
    rectEditDebug("EditableAxisAlignedRectangle mount")
    return () => rectEditDebug("EditableAxisAlignedRectangle unmount")
  }, [])

  const cornerIcon = useMemo(
    () =>
      L.divIcon({
        className: "",
        html: `<div style="
        width: 12px;
        height: 12px;
        border-radius: 3px;
        background: #1d4ed8;
        border: 2px solid #ffffff;
        box-shadow: 0 1px 2px rgba(0,0,0,0.25);
      "></div>`,
        iconSize: [12, 12],
        iconAnchor: [6, 6],
      }),
    [],
  )

  const sw = leafletBounds.getSouthWest()
  const ne = leafletBounds.getNorthEast()
  const nw = L.latLng(ne.lat, sw.lng)
  const se = L.latLng(sw.lat, ne.lng)

  const corners: Array<{ key: string; position: L.LatLng; kind: "sw" | "se" | "ne" | "nw" }> = [
    { key: "sw", position: sw, kind: "sw" },
    { key: "se", position: se, kind: "se" },
    { key: "ne", position: ne, kind: "ne" },
    { key: "nw", position: nw, kind: "nw" },
  ]

  // react-leaflet Marker updates with `props.position !== prevProps.position` (reference).
  // A fresh [lat, lng] array every render forces setLatLng and kills Leaflet drag on the active handle.
  const cornerPositions = useMemo(
    () =>
      ({
        sw: [sw.lat, sw.lng] as [number, number],
        se: [se.lat, se.lng] as [number, number],
        ne: [ne.lat, ne.lng] as [number, number],
        nw: [nw.lat, nw.lng] as [number, number],
      }) as const,
    [sw.lat, sw.lng, se.lat, se.lng, ne.lat, ne.lng, nw.lat, nw.lng],
  )

  /** While dragging a corner, keep one stable [lat,lng] tuple ref for that Marker only. */
  const cornerDragFreezeRef = useRef<{ kind: "sw" | "se" | "ne" | "nw"; pos: [number, number] } | null>(null)

  const onChangeRef = useRef(onChange)
  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  const applyCornerDrag = (kind: "sw" | "se" | "ne" | "nw", latlng: L.LatLng) => {
    let west = Math.min(sw.lng, ne.lng)
    let east = Math.max(sw.lng, ne.lng)
    let south = Math.min(sw.lat, ne.lat)
    let north = Math.max(sw.lat, ne.lat)

    const lng = latlng.lng
    const lat = latlng.lat
    if (!isFiniteNumber(lng) || !isFiniteNumber(lat)) return

    if (kind === "sw") {
      west = Math.min(lng, east)
      south = Math.min(lat, north)
    } else if (kind === "se") {
      east = Math.max(lng, west)
      south = Math.min(lat, north)
    } else if (kind === "ne") {
      east = Math.max(lng, west)
      north = Math.max(lat, south)
    } else {
      west = Math.min(lng, east)
      north = Math.max(lat, south)
    }

    if (Math.abs(east - west) < 1e-12 || Math.abs(north - south) < 1e-12) return

    onChangeRef.current({
      southWest: { lat: south, lng: west },
      northEast: { lat: north, lng: east },
    })
  }

  const translateRef = useRef<{
    startLatLng: L.LatLng
    startWest: number
    startSouth: number
    startEast: number
    startNorth: number
  } | null>(null)

  const translateMoveListenerRef = useRef<(ev: MouseEvent) => void>(() => {})
  const translateUpListenerRef = useRef<() => void>(() => {})

  const detachTranslateListeners = useCallback(() => {
    L.DomEvent.off(document as any, "mousemove", translateMoveListenerRef.current as any)
    L.DomEvent.off(document as any, "mouseup", translateUpListenerRef.current as any)
  }, [])

  const endTranslate = useCallback(() => {
    translateRef.current = null
    detachTranslateListeners()
    try {
      map.dragging?.enable()
    } catch {
      // ignore
    }
  }, [detachTranslateListeners, map])

  translateMoveListenerRef.current = (ev: MouseEvent) => {
    const state = translateRef.current
    if (!state) return
    const cur = map.mouseEventToLatLng(ev)
    if (!cur || !isFiniteNumber(cur.lat) || !isFiniteNumber(cur.lng)) return

    const dLng = cur.lng - state.startLatLng.lng
    const dLat = cur.lat - state.startLatLng.lat

    const west = state.startWest + dLng
    const east = state.startEast + dLng
    const south = state.startSouth + dLat
    const north = state.startNorth + dLat

    if (Math.abs(east - west) < 1e-12 || Math.abs(north - south) < 1e-12) return

    onChangeRef.current({
      southWest: { lat: south, lng: west },
      northEast: { lat: north, lng: east },
    })
  }

  translateUpListenerRef.current = () => {
    endTranslate()
  }

  useEffect(() => {
    return () => {
      endTranslate()
    }
  }, [endTranslate])

  return (
    <>
      <Rectangle
        bounds={leafletBounds as any}
        pathOptions={{ color: "#1d4ed8", weight: 2, fillColor: "#3b82f6", fillOpacity: 0.18 }}
        eventHandlers={{
          mousedown: (e: any) => {
            if (rectangleDrawingRef.current) return
            const latlng = e?.latlng
            if (!latlng || !isFiniteNumber(latlng.lat) || !isFiniteNumber(latlng.lng)) return

            const west = Math.min(sw.lng, ne.lng)
            const east = Math.max(sw.lng, ne.lng)
            const south = Math.min(sw.lat, ne.lat)
            const north = Math.max(sw.lat, ne.lat)

            translateRef.current = {
              startLatLng: latlng,
              startWest: west,
              startSouth: south,
              startEast: east,
              startNorth: north,
            }

            try {
              map.dragging?.disable()
            } catch {
              // ignore
            }

            L.DomEvent.on(document as any, "mousemove", translateMoveListenerRef.current as any)
            L.DomEvent.on(document as any, "mouseup", translateUpListenerRef.current as any)
          },
        }}
      />

      {corners.map((c) => {
        const freeze = cornerDragFreezeRef.current
        const position: [number, number] = freeze?.kind === c.kind ? freeze.pos : cornerPositions[c.kind]

        return (
          <Marker
            key={c.key}
            position={position}
            draggable
            icon={cornerIcon as any}
            eventHandlers={{
              mousedown: (e: any) => {
                const original = e?.originalEvent as MouseEvent | undefined
                if (original) {
                  L.DomEvent.stop(original)
                }
              },
              dragstart: (e: any) => {
                const ll = e?.target?.getLatLng?.()
                if (!ll || !isFiniteNumber(ll.lat) || !isFiniteNumber(ll.lng)) return
                const pos: [number, number] = [ll.lat, ll.lng]
                cornerDragFreezeRef.current = { kind: c.kind, pos }
                rectEditDebug("corner dragstart", c.kind, pos)
              },
              drag: (e: any) => {
                const ll = e?.target?.getLatLng?.()
                if (!ll || !isFiniteNumber(ll.lat) || !isFiniteNumber(ll.lng)) return
                rectEditDebug("corner drag", c.kind, [ll.lat, ll.lng])
                applyCornerDrag(c.kind, ll)
              },
              dragend: (e: any) => {
                cornerDragFreezeRef.current = null
                const ll = e?.target?.getLatLng?.()
                if (!ll || !isFiniteNumber(ll.lat) || !isFiniteNumber(ll.lng)) return
                rectEditDebug("corner dragend", c.kind, [ll.lat, ll.lng])
                applyCornerDrag(c.kind, ll)
              },
            }}
          />
        )
      })}
    </>
  )
}

export function LeafletMap({
  points,
  polygons,
  height = 420,
  emptyState,
  onFeatureClick,
  fitToData = true,
  initialCenter = null,
  initialZoom = null,
  showPopups = true,
  onMapClick,
  editablePoint = null,
  rectanglePreview = null,
  editableRectangle = null,
  rectangleDraw = null,
  interactiveWhenEmpty = false,
  tileUrl = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  tileAttribution = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}: LeafletMapProps) {
  const [error, setError] = useState<string | null>(null)
  const clickHandlerRef = useRef(onFeatureClick)
  const rectangleDrawingRef = useRef(false)
  const rectangleDrawRef = useRef(rectangleDraw)
  useEffect(() => {
    clickHandlerRef.current = onFeatureClick
  }, [onFeatureClick])

  useEffect(() => {
    rectangleDrawRef.current = rectangleDraw
  }, [rectangleDraw])

  useEffect(() => {
    if (!rectangleDraw?.enabled) rectangleDrawingRef.current = false
  }, [rectangleDraw?.enabled])

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

  const polygonPaths = useMemo(() => {
    return normalizedPolygons.features
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
  }, [normalizedPolygons])

  const previewLeafletBounds = useMemo(() => {
    if (!rectanglePreview) return null
    const sw = rectanglePreview.southWest
    const ne = rectanglePreview.northEast
    if (!isFiniteNumber(sw.lat) || !isFiniteNumber(sw.lng) || !isFiniteNumber(ne.lat) || !isFiniteNumber(ne.lng)) return null
    return L.latLngBounds(L.latLng(sw.lat, sw.lng), L.latLng(ne.lat, ne.lng))
  }, [rectanglePreview])

  const editableLeafletBounds = useMemo(() => {
    if (!editableRectangle) return null
    const sw = editableRectangle.southWest
    const ne = editableRectangle.northEast
    if (!isFiniteNumber(sw.lat) || !isFiniteNumber(sw.lng) || !isFiniteNumber(ne.lat) || !isFiniteNumber(ne.lng)) return null
    return L.latLngBounds(L.latLng(sw.lat, sw.lng), L.latLng(ne.lat, ne.lng))
  }, [
    editableRectangle?.southWest.lat,
    editableRectangle?.southWest.lng,
    editableRectangle?.northEast.lat,
    editableRectangle?.northEast.lng,
  ])

  const extraFitBounds = previewLeafletBounds ?? editableLeafletBounds

  const hasAny =
    normalizedPoints.features.length > 0 ||
    polygonPaths.length > 0 ||
    !!previewLeafletBounds ||
    !!editableLeafletBounds ||
    !!rectangleDraw?.enabled ||
    !!interactiveWhenEmpty

  const bounds = useMemo(
    () => (fitToData ? extractLatLngBounds([normalizedPoints, normalizedPolygons], extraFitBounds) : null),
    [fitToData, normalizedPoints, normalizedPolygons, extraFitBounds],
  )

  useEffect(() => {
    // If callers pass bad data, prefer a soft error state over crashing during render.
    // (normalizeFeatureCollection already strips most invalid shapes.)
    setError(null)
  }, [points, polygons])

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

  if (!hasAny) {
    return (
      <div style={{ height }} className="rounded-md border border-dashed border-muted flex items-center justify-center">
        {emptyState ?? <div className="text-sm text-muted-foreground">No geographic features.</div>}
      </div>
    )
  }

  return (
    <div className="rounded-md overflow-hidden border border-border" style={{ height }}>
      {error ? <div className="p-3 text-sm text-destructive">{error}</div> : null}
      <MapContainer
        center={(initialCenter ?? DEFAULT_CENTER) as any}
        zoom={(initialZoom ?? DEFAULT_ZOOM) as any}
        style={{ height: "100%", width: "100%" }}
      >
        <MapClickHandler onMapClick={onMapClick} rectangleDrawingRef={rectangleDrawingRef} />
        {rectangleDraw?.enabled ? (
          <RectangleDrawController rectangleDrawRef={rectangleDrawRef} rectangleDrawingRef={rectangleDrawingRef} />
        ) : null}
        <TileLayer attribution={tileAttribution} url={tileUrl} />
        {previewLeafletBounds ? (
          <Rectangle
            bounds={previewLeafletBounds as any}
            pathOptions={{
              color: "#1d4ed8",
              weight: 2,
              fillColor: "#3b82f6",
              fillOpacity: 0.12,
              dashArray: "6 6",
            }}
          />
        ) : null}
        {editableLeafletBounds && editableRectangle ? (
          <EditableAxisAlignedRectangle
            leafletBounds={editableLeafletBounds}
            onChange={editableRectangle.onChange}
            rectangleDrawingRef={rectangleDrawingRef}
          />
        ) : null}
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

