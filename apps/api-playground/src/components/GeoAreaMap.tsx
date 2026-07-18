import { useEffect, useRef, useState } from "react"
import {
  Circle,
  CircleMarker,
  MapContainer,
  Rectangle,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet"
import type { LeafletMouseEvent } from "leaflet"
import L from "leaflet"
import "leaflet/dist/leaflet.css"

import {
  bboxFromCorners,
  bboxToLeafletBounds,
  bboxToValue,
  DEFAULT_MAP_CENTER,
  parseBbox,
  validCenter,
  type BoundingBox,
  type MapCenter,
} from "../lib/mapSelection"

type GeoMode = "bbox" | "point"

interface GeoAreaMapProps {
  bbox: string
  centerLat: string
  centerLng: string
  radiusMiles: string
  supportsPoint: boolean
  onChange: (values: {
    bbox?: string
    centerLat?: string
    centerLng?: string
    radiusMiles?: string
  }) => void
}

function FitSelection({
  bbox,
  center,
}: {
  bbox: BoundingBox | null
  center: MapCenter | null
}) {
  const map = useMap()

  useEffect(() => {
    if (bbox) {
      map.fitBounds(bboxToLeafletBounds(bbox), { padding: [24, 24], maxZoom: 14 })
    } else if (center) {
      map.setView([center.lat, center.lng], Math.max(map.getZoom(), 11))
    }
  }, [bbox, center, map])

  return null
}

function AreaInteraction({
  mode,
  bbox,
  onBboxChange,
  onPointChange,
}: {
  mode: GeoMode
  bbox: BoundingBox | null
  onBboxChange: (bbox: BoundingBox) => void
  onPointChange: (center: MapCenter) => void
}) {
  const map = useMap()
  const dragStart = useRef<L.LatLng | null>(null)
  const [preview, setPreview] = useState<BoundingBox | null>(null)

  useMapEvents({
    click(event) {
      if (mode === "point") {
        onPointChange({ lat: event.latlng.lat, lng: event.latlng.lng })
      }
    },
    mousedown(event: LeafletMouseEvent) {
      if (mode !== "bbox" || !event.originalEvent.shiftKey) return
      L.DomEvent.stopPropagation(event)
      L.DomEvent.preventDefault(event.originalEvent)
      map.dragging.disable()
      dragStart.current = event.latlng
      setPreview(
        bboxFromCorners(
          { lat: event.latlng.lat, lng: event.latlng.lng },
          { lat: event.latlng.lat, lng: event.latlng.lng },
        ),
      )
    },
    mousemove(event: LeafletMouseEvent) {
      if (!dragStart.current) return
      setPreview(
        bboxFromCorners(
          { lat: dragStart.current.lat, lng: dragStart.current.lng },
          { lat: event.latlng.lat, lng: event.latlng.lng },
        ),
      )
    },
    mouseup(event: LeafletMouseEvent) {
      if (!dragStart.current) return
      map.dragging.enable()
      const next = bboxFromCorners(
        { lat: dragStart.current.lat, lng: dragStart.current.lng },
        { lat: event.latlng.lat, lng: event.latlng.lng },
      )
      dragStart.current = null
      setPreview(null)
      if (next.maxLat - next.minLat > 0.0005 && next.maxLng - next.minLng > 0.0005) {
        onBboxChange(next)
      }
    },
  })

  const shownBox = preview ?? bbox
  return shownBox && mode === "bbox" ? (
    <Rectangle
      bounds={bboxToLeafletBounds(shownBox)}
      pathOptions={{
        color: "#dc2626",
        weight: 2,
        fillColor: "#ef4444",
        fillOpacity: 0.12,
      }}
    />
  ) : null
}

export default function GeoAreaMap({
  bbox: bboxValue,
  centerLat,
  centerLng,
  radiusMiles,
  supportsPoint,
  onChange,
}: GeoAreaMapProps) {
  const bbox = parseBbox(bboxValue)
  const center = validCenter(centerLat, centerLng)
  const [mode, setMode] = useState<GeoMode>(
    supportsPoint && center && !bbox ? "point" : "bbox",
  )
  const radius = Number(radiusMiles)

  useEffect(() => {
    if (bbox) setMode("bbox")
    else if (supportsPoint && center) setMode("point")
  }, [bbox, center, supportsPoint])

  function chooseMode(nextMode: GeoMode) {
    setMode(nextMode)
    if (nextMode === "bbox") {
      onChange({ centerLat: "", centerLng: "", radiusMiles: "" })
    } else {
      onChange({ bbox: "" })
    }
  }

  return (
    <div className="map-selector" aria-label="Geographic area map">
      <div className="map-selector-toolbar">
        {supportsPoint && (
          <div className="map-selector-modes" aria-label="Selection mode">
            <button
              type="button"
              className={mode === "bbox" ? "active" : ""}
              aria-pressed={mode === "bbox"}
              onClick={() => chooseMode("bbox")}
            >
              Bounding box
            </button>
            <button
              type="button"
              className={mode === "point" ? "active" : ""}
              aria-pressed={mode === "point"}
              onClick={() => chooseMode("point")}
            >
              Point and radius
            </button>
          </div>
        )}
        {(bbox || center) && (
          <button
            type="button"
            className="map-selector-clear"
            onClick={() =>
              onChange({ bbox: "", centerLat: "", centerLng: "", radiusMiles: "" })
            }
          >
            Clear selection
          </button>
        )}
      </div>

      <div className="map-selector-frame">
        <MapContainer
          center={[center?.lat ?? DEFAULT_MAP_CENTER.lat, center?.lng ?? DEFAULT_MAP_CENTER.lng]}
          zoom={11}
          scrollWheelZoom
          className="map-selector-map"
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
            attribution=""
          />
          <AreaInteraction
            mode={mode}
            bbox={bbox}
            onBboxChange={(next) => onChange({ bbox: bboxToValue(next) })}
            onPointChange={(next) =>
              onChange({
                centerLat: String(Number(next.lat.toFixed(6))),
                centerLng: String(Number(next.lng.toFixed(6))),
                radiusMiles: radiusMiles || "5",
              })
            }
          />
          <FitSelection bbox={mode === "bbox" ? bbox : null} center={mode === "point" ? center : null} />
          {mode === "point" && center && (
            <>
              <CircleMarker
                center={[center.lat, center.lng]}
                radius={6}
                pathOptions={{ color: "#1d4ed8", fillColor: "#2563eb", fillOpacity: 1 }}
              />
              {Number.isFinite(radius) && radius > 0 && (
                <Circle
                  center={[center.lat, center.lng]}
                  radius={radius * 1609.344}
                  pathOptions={{ color: "#2563eb", fillColor: "#3b82f6", fillOpacity: 0.12 }}
                />
              )}
            </>
          )}
        </MapContainer>
      </div>

      <p className="map-selector-help">
        {mode === "bbox"
          ? "Hold Shift and drag to draw a search box."
          : "Click the map to choose the center; set the radius in the field below."}
      </p>
    </div>
  )
}
