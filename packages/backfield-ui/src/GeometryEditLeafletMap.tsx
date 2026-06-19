import { useEffect, useState } from "react"
import {
  boundsFromPolygonGeometry,
  isAxisAlignedRectanglePolygon,
  polygonFromAxisAlignedBounds,
} from "./axisAlignedRectangle"
import { LeafletMap, type LeafletMapFeatureClick, type LeafletMapProps } from "./LeafletMap"

const ADD_GEOMETRY_MAP_CENTER: [number, number] = [39.8283, -98.5795]
const ADD_GEOMETRY_MAP_ZOOM = 3

const EDIT_TILE = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
const EDIT_ATTR =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'

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

function axisAlignedRectangleDraft(geometry: Record<string, unknown> | null): boolean {
  if (!isPolygonGeometry(geometry)) return false
  return isAxisAlignedRectanglePolygon(geometry)
}

export type GeometryEditLeafletMapProps = {
  points: LeafletMapProps["points"]
  polygons: LeafletMapProps["polygons"]
  height?: number
  /** When true, map fills parent height (see ``LeafletMap`` ``fillHeight``). */
  fillHeight?: boolean
  /** When true, enables edit handles and disables auto fitBounds during drags. */
  geometryEditing: boolean
  /** Place search control (defaults to ``geometryEditing``). Disable for simple rectangle-only editors. */
  geocoder?: boolean
  geometryDraft: Record<string, unknown> | null
  onGeometryDraftChange: (g: Record<string, unknown> | null) => void
  geometryAddMode: "point" | "rectangle" | null
  onGeometryAddModeChange: (mode: "point" | "rectangle" | null) => void
  /** ``properties.id`` of the Point feature to drag (e.g. ``canonical`` or review anchor id). */
  editPointFeatureId?: string | null
  /** Fit once when ``focusBoundsKey`` bumps (place selected or edit mode entered). */
  focusBounds?: [[number, number], [number, number]] | null
  focusBoundsKey?: number
  initialCenter?: [number, number] | null
  initialZoom?: number | null
  onFeatureClick?: (ev: LeafletMapFeatureClick) => void
  showPopups?: boolean
  /** Optional controlled rectangle-draw preview (Stylebook canonical layer hiding). */
  rectanglePreview?: {
    southWest: { lat: number; lng: number }
    northEast: { lat: number; lng: number }
  } | null
  onRectanglePreviewChange?: (
    preview: {
      southWest: { lat: number; lng: number }
      northEast: { lat: number; lng: number }
    } | null,
  ) => void
}

/**
 * Leaflet map for editing a single place geometry (point or axis-aligned rectangle).
 * Matches Stylebook canonical detail behavior: no fitBounds while dragging handles.
 */
export function GeometryEditLeafletMap({
  points,
  polygons,
  height = 420,
  fillHeight = false,
  geometryEditing,
  geocoder,
  geometryDraft,
  onGeometryDraftChange,
  geometryAddMode,
  onGeometryAddModeChange,
  editPointFeatureId = null,
  focusBounds = null,
  focusBoundsKey = 0,
  initialCenter = null,
  initialZoom = null,
  onFeatureClick,
  showPopups = false,
  rectanglePreview: rectanglePreviewProp,
  onRectanglePreviewChange,
}: GeometryEditLeafletMapProps) {
  const [internalRectanglePreview, setInternalRectanglePreview] = useState<{
    southWest: { lat: number; lng: number }
    northEast: { lat: number; lng: number }
  } | null>(null)
  const rectanglePreview =
    rectanglePreviewProp !== undefined ? rectanglePreviewProp : internalRectanglePreview
  const setRectanglePreview = onRectanglePreviewChange ?? setInternalRectanglePreview

  useEffect(() => {
    if (!geometryEditing) {
      if (onRectanglePreviewChange) onRectanglePreviewChange(null)
      else setInternalRectanglePreview(null)
    }
  }, [geometryEditing, onRectanglePreviewChange])

  const addModeCenter =
    geometryEditing &&
    !geometryDraft &&
    (geometryAddMode === "point" || geometryAddMode === "rectangle")
      ? ADD_GEOMETRY_MAP_CENTER
      : null
  const addModeZoom =
    geometryEditing &&
    !geometryDraft &&
    (geometryAddMode === "point" || geometryAddMode === "rectangle")
      ? ADD_GEOMETRY_MAP_ZOOM
      : null

  return (
    <LeafletMap
      height={height}
      fillHeight={fillHeight}
      points={points}
      polygons={polygons}
      geocoder={geocoder ?? geometryEditing}
      showPopups={showPopups}
      // While editing, geometry updates constantly (drag/resize). Auto fitBounds would fight manual zoom.
      fitToData={!geometryEditing && !focusBounds}
      focusBounds={focusBounds}
      focusBoundsKey={focusBoundsKey}
      initialCenter={addModeCenter ?? initialCenter}
      initialZoom={addModeZoom ?? initialZoom}
      interactiveWhenEmpty={geometryEditing && geometryAddMode === "point" && !geometryDraft}
      tileUrl={geometryEditing ? EDIT_TILE : undefined}
      tileAttribution={geometryEditing ? EDIT_ATTR : undefined}
      onFeatureClick={onFeatureClick}
      onMapClick={
        geometryEditing &&
        geometryAddMode === "point" &&
        (!geometryDraft || isPointGeometry(geometryDraft))
          ? ({ latlng }) => {
              onGeometryDraftChange({ type: "Point", coordinates: [latlng.lng, latlng.lat] })
              onGeometryAddModeChange(null)
            }
          : undefined
      }
      editablePoint={
        geometryEditing &&
        editPointFeatureId &&
        isPointGeometry(geometryDraft) &&
        geometryAddMode !== "rectangle"
          ? {
              featureId: editPointFeatureId,
              onChange: ({ lng, lat }) => {
                onGeometryDraftChange({ type: "Point", coordinates: [lng, lat] })
              },
            }
          : null
      }
      rectanglePreview={geometryEditing ? rectanglePreview : null}
      editableRectangle={
        geometryEditing &&
        isPolygonGeometry(geometryDraft) &&
        axisAlignedRectangleDraft(geometryDraft) &&
        geometryAddMode !== "rectangle" &&
        boundsFromPolygonGeometry(geometryDraft as any)
          ? (() => {
              const b = boundsFromPolygonGeometry(geometryDraft as any)!
              return {
                southWest: { lat: b.south, lng: b.west },
                northEast: { lat: b.north, lng: b.east },
                onChange: (next) => {
                  onGeometryDraftChange(
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
                onGeometryDraftChange(
                  polygonFromAxisAlignedBounds({
                    west: bounds.southWest.lng,
                    south: bounds.southWest.lat,
                    east: bounds.northEast.lng,
                    north: bounds.northEast.lat,
                  }) as any,
                )
                setRectanglePreview(null)
                onGeometryAddModeChange(null)
              },
            }
          : null
      }
    />
  )
}
