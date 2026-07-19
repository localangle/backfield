import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
  type ReactNode,
} from "react"
import { MapContainer, Polygon, TileLayer, useMap, useMapEvents } from "react-leaflet"
import type { LatLng, LeafletMouseEvent, Map as LeafletMap } from "leaflet"
import L from "leaflet"
import "leaflet/dist/leaflet.css"

import {
  cellBoundary,
  cellAtPoint,
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

const MIN_PAINT_DRAG_PX = 6

interface ShiftPaintContextValue {
  begin: (event: LeafletMouseEvent) => void
  isDragging: () => boolean
  paintCell: (cell: string) => void
  shouldSuppressClick: () => boolean
}

const ShiftPaintContext = createContext<ShiftPaintContextValue | null>(null)

function isValidLatLng(latlng: LatLng | null | undefined): latlng is LatLng {
  return (
    latlng !== null &&
    latlng !== undefined &&
    Number.isFinite(latlng.lat) &&
    Number.isFinite(latlng.lng)
  )
}

function mouseEventToMapLatLng(map: LeafletMap, event: MouseEvent): LatLng | null {
  const bounds = map.getContainer().getBoundingClientRect()
  const point = L.point(
    Math.max(0, Math.min(bounds.width, event.clientX - bounds.left)),
    Math.max(0, Math.min(bounds.height, event.clientY - bounds.top)),
  )
  const latlng = map.containerPointToLatLng(point)
  return isValidLatLng(latlng) ? latlng : null
}

function cancelPaint(
  map: LeafletMap,
  draggingRef: MutableRefObject<boolean>,
  paintedCellsRef: MutableRefObject<Set<string>>,
  startPointRef: MutableRefObject<L.Point | null>,
) {
  draggingRef.current = false
  paintedCellsRef.current.clear()
  startPointRef.current = null
  map.dragging.enable()
}

function ShiftPaintLayer({
  resolution,
  onPaintCell,
  children,
}: {
  resolution: number
  onPaintCell: (cell: string) => void
  children: ReactNode
}) {
  const map = useMap()
  const draggingRef = useRef(false)
  const paintedCellsRef = useRef<Set<string>>(new Set())
  const startPointRef = useRef<L.Point | null>(null)
  const suppressClickRef = useRef(false)

  const paintCell = useCallback(
    (cell: string) => {
      if (!draggingRef.current || paintedCellsRef.current.has(cell)) return
      paintedCellsRef.current.add(cell)
      onPaintCell(cell)
    },
    [onPaintCell],
  )

  const paintAtLatLng = useCallback(
    (latlng: LatLng) => {
      try {
        paintCell(cellAtPoint(latlng.lat, latlng.lng, resolution))
      } catch {
        // Ignore pointer positions that H3 cannot represent.
      }
    },
    [paintCell, resolution],
  )

  const begin = useCallback(
    (event: LeafletMouseEvent) => {
      if (!event.originalEvent.shiftKey || !isValidLatLng(event.latlng)) return
      L.DomEvent.stop(event.originalEvent)
      draggingRef.current = true
      paintedCellsRef.current.clear()
      const latlng = L.latLng(event.latlng.lat, event.latlng.lng)
      startPointRef.current = map.latLngToContainerPoint(latlng)
      map.dragging.disable()
      paintAtLatLng(latlng)
    },
    [map, paintAtLatLng],
  )

  const finish = useCallback(
    (point: L.Point) => {
      if (!draggingRef.current) return
      const startPoint = startPointRef.current
      if (startPoint && startPoint.distanceTo(point) >= MIN_PAINT_DRAG_PX) {
        suppressClickRef.current = true
        window.setTimeout(() => {
          suppressClickRef.current = false
        }, 0)
      }
      cancelPaint(map, draggingRef, paintedCellsRef, startPointRef)
    },
    [map],
  )

  useMapEvents({
    mousedown(event) {
      if (event.originalEvent.shiftKey) begin(event)
      else if (draggingRef.current) {
        cancelPaint(map, draggingRef, paintedCellsRef, startPointRef)
      }
    },
  })

  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      if (!draggingRef.current) return
      const latlng = mouseEventToMapLatLng(map, event)
      if (latlng) paintAtLatLng(latlng)
    }
    const onUp = (event: MouseEvent) => {
      if (!draggingRef.current) return
      const bounds = map.getContainer().getBoundingClientRect()
      finish(
        L.point(
          Math.max(0, Math.min(bounds.width, event.clientX - bounds.left)),
          Math.max(0, Math.min(bounds.height, event.clientY - bounds.top)),
        ),
      )
    }
    window.addEventListener("mousemove", onMove)
    window.addEventListener("mouseup", onUp)
    return () => {
      window.removeEventListener("mousemove", onMove)
      window.removeEventListener("mouseup", onUp)
    }
  }, [finish, map, paintAtLatLng])

  const value = useMemo<ShiftPaintContextValue>(
    () => ({
      begin,
      isDragging: () => draggingRef.current,
      paintCell,
      shouldSuppressClick: () => suppressClickRef.current,
    }),
    [begin, paintCell],
  )

  return <ShiftPaintContext.Provider value={value}>{children}</ShiftPaintContext.Provider>
}

function useShiftPaint() {
  return useContext(ShiftPaintContext)
}

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
  const mountedRef = useRef(false)
  const previousResolutionRef = useRef(resolution)

  useEffect(() => {
    const zoom = zoomForResolution(resolution)
    map.setMinZoom(zoom)
    map.setMaxZoom(zoom)
    const resolutionChanged = previousResolutionRef.current !== resolution
    previousResolutionRef.current = resolution

    if (!mountedRef.current) {
      mountedRef.current = true
      map.setView([center.lat, center.lng], zoom, { animate: false })
    } else if (resolutionChanged) {
      map.setView([center.lat, center.lng], zoom, { animate: true })
    }
  }, [center.lat, center.lng, map, resolution])

  return null
}

function H3Grid({
  resolution,
  selectedCells,
  onToggleCell,
}: {
  resolution: number
  selectedCells: string[]
  onToggleCell: (cell: string) => void
}) {
  const map = useMap()
  const shiftPaint = useShiftPaint()
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
              mousedown: (event: LeafletMouseEvent) => {
                if (event.originalEvent.shiftKey) shiftPaint?.begin(event)
              },
              mouseover: () => {
                if (shiftPaint?.isDragging()) shiftPaint.paintCell(cell)
              },
              click: (event: LeafletMouseEvent) => {
                if (shiftPaint?.shouldSuppressClick() || shiftPaint?.isDragging()) return
                L.DomEvent.stopPropagation(event)
                onToggleCell(cell)
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
  const cellsRef = useRef(cells)
  cellsRef.current = cells

  const changeCells = useCallback(
    (nextCells: string[]) => {
      cellsRef.current = nextCells
      onChange(nextCells, activeResolution)
    },
    [activeResolution, onChange],
  )

  const toggleCell = useCallback(
    (cell: string) => {
      const current = cellsRef.current
      if (!multiple) {
        changeCells(current[0] === cell ? [] : [cell])
        return
      }
      changeCells(
        current.includes(cell)
          ? current.filter((selectedCell) => selectedCell !== cell)
          : [...current, cell],
      )
    },
    [changeCells, multiple],
  )

  const paintCell = useCallback(
    (cell: string) => {
      const current = cellsRef.current
      if (!multiple) {
        changeCells([cell])
      } else if (!current.includes(cell)) {
        changeCells([...current, cell])
      }
    },
    [changeCells, multiple],
  )

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
                cellsRef.current = []
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
            onClick={() => changeCells([])}
          >
            Clear {multiple ? "cells" : "cell"}
          </button>
        )}
      </div>

      <div className="map-selector-frame">
        <MapContainer
          center={[center.lat, center.lng]}
          zoom={zoomForResolution(activeResolution)}
          minZoom={zoomForResolution(activeResolution)}
          maxZoom={zoomForResolution(activeResolution)}
          scrollWheelZoom={false}
          doubleClickZoom={false}
          touchZoom={false}
          keyboard={false}
          boxZoom={false}
          zoomControl={false}
          className="map-selector-map"
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
            attribution=""
          />
          <MapViewSync center={center} resolution={activeResolution} />
          <ShiftPaintLayer resolution={activeResolution} onPaintCell={paintCell}>
            <H3Grid
              resolution={activeResolution}
              selectedCells={cells}
              onToggleCell={toggleCell}
            />
          </ShiftPaintLayer>
        </MapContainer>
      </div>

      <p className="map-selector-help">
        Click {multiple ? "hexes" : "a hex"} to toggle highlighting, or hold Shift and drag to
        highlight {multiple ? "several cells" : "a cell"}. Drag normally to pan.
      </p>
    </div>
  )
}
