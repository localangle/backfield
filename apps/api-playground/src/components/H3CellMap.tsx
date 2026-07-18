import { useCallback, useEffect, useMemo, useState } from "react"
import { MapContainer, Polygon, TileLayer, useMap, useMapEvents } from "react-leaflet"
import type { LeafletMouseEvent } from "leaflet"
import L from "leaflet"
import "leaflet/dist/leaflet.css"

import {
  cellBoundary,
  cellResolution,
  cellsForBounds,
  centerFromCells,
  DEFAULT_MAP_CENTER,
} from "../lib/mapSelection"

const RESOLUTION_OPTIONS = [
  { resolution: 9, label: "Block", zoom: 13 },
  { resolution: 8, label: "Neighborhood", zoom: 12 },
  { resolution: 6, label: "City", zoom: 9 },
  { resolution: 5, label: "Region", zoom: 8 },
  { resolution: 4, label: "National", zoom: 6 },
]

function zoomForResolution(resolution: number): number {
  return (
    RESOLUTION_OPTIONS.find((option) => option.resolution === resolution)?.zoom ??
    Math.max(3, Math.min(15, resolution + 3))
  )
}

function MapViewSync({
  center,
  resolution,
}: {
  center: { lat: number; lng: number }
  resolution: number
}) {
  const map = useMap()

  useEffect(() => {
    map.setView([center.lat, center.lng], zoomForResolution(resolution), {
      animate: false,
    })
  }, [center.lat, center.lng, map, resolution])

  return null
}

function H3Grid({
  resolution,
  selectedCells,
  multiple,
  onChange,
}: {
  resolution: number
  selectedCells: string[]
  multiple: boolean
  onChange: (cells: string[]) => void
}) {
  const map = useMap()
  const [visibleCells, setVisibleCells] = useState<string[]>([])
  const selected = useMemo(() => new Set(selectedCells), [selectedCells])

  const refresh = useCallback(() => {
    const bounds = map.getBounds()
    setVisibleCells(
      cellsForBounds(
        {
          south: bounds.getSouth(),
          north: bounds.getNorth(),
          west: bounds.getWest(),
          east: bounds.getEast(),
        },
        resolution,
      ),
    )
  }, [map, resolution])

  useMapEvents({
    moveend: refresh,
    zoomend: refresh,
  })

  useEffect(() => {
    const timer = window.setTimeout(refresh, 0)
    return () => window.clearTimeout(timer)
  }, [refresh])

  const allCells = [...new Set([...visibleCells, ...selectedCells])]

  return (
    <>
      {allCells.map((cell) => {
        let boundary: [number, number][]
        try {
          boundary = cellBoundary(cell)
        } catch {
          return null
        }
        const isSelected = selected.has(cell)
        return (
          <Polygon
            key={cell}
            positions={boundary}
            pathOptions={{
              color: isSelected ? "#1d4ed8" : "rgba(100, 116, 139, 0.5)",
              weight: isSelected ? 1.5 : 0.6,
              fillColor: isSelected ? "#2563eb" : "#e2e8f0",
              fillOpacity: isSelected ? 0.45 : 0.22,
            }}
            eventHandlers={{
              click: (event: LeafletMouseEvent) => {
                L.DomEvent.stopPropagation(event)
                if (!multiple) {
                  onChange(isSelected ? [] : [cell])
                } else {
                  onChange(
                    isSelected
                      ? selectedCells.filter((selectedCell) => selectedCell !== cell)
                      : [...selectedCells, cell],
                  )
                }
              },
            }}
          />
        )
      })}
    </>
  )
}

interface H3CellMapProps {
  cells: string[]
  resolution: number
  multiple?: boolean
  onChange: (cells: string[], resolution: number) => void
}

export default function H3CellMap({
  cells,
  resolution,
  multiple = true,
  onChange,
}: H3CellMapProps) {
  const selectedResolution = cells[0] ? cellResolution(cells[0]) : null
  const [activeResolution, setActiveResolution] = useState(
    selectedResolution ?? resolution,
  )
  useEffect(() => {
    setActiveResolution(selectedResolution ?? resolution)
  }, [resolution, selectedResolution])
  const center = centerFromCells(cells) ?? DEFAULT_MAP_CENTER

  return (
    <div className="map-selector" aria-label="H3 cell map">
      <div className="map-selector-toolbar">
        <div className="map-selector-resolution" aria-label="H3 resolution">
          <span>Resolution</span>
          {RESOLUTION_OPTIONS.map((option) => (
            <button
              key={option.resolution}
              type="button"
              className={activeResolution === option.resolution ? "active" : ""}
              aria-pressed={activeResolution === option.resolution}
              onClick={() => {
                setActiveResolution(option.resolution)
                onChange([], option.resolution)
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
        {cells.length > 0 && (
          <button
            type="button"
            className="map-selector-clear"
            onClick={() => onChange([], activeResolution)}
          >
            Clear {multiple ? "cells" : "cell"}
          </button>
        )}
      </div>

      <div className="map-selector-frame">
        <MapContainer
          center={[center.lat, center.lng]}
          zoom={zoomForResolution(activeResolution)}
          scrollWheelZoom={false}
          doubleClickZoom={false}
          className="map-selector-map"
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
            attribution=""
          />
          <MapViewSync center={center} resolution={activeResolution} />
          <H3Grid
            resolution={activeResolution}
            selectedCells={cells}
            multiple={multiple}
            onChange={(nextCells) => onChange(nextCells, activeResolution)}
          />
        </MapContainer>
      </div>

      <p className="map-selector-help">
        Click {multiple ? "hexes" : "a hex"} to {multiple ? "add or remove cells" : "select a cell"}.
        Pan the map to browse another area.
      </p>
    </div>
  )
}
