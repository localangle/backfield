import { useMemo, useState } from 'react'
import { LeafletMap } from '@backfield/ui/LeafletMap'
import {
  boundsFromPolygonGeometry,
  isAxisAlignedRectanglePolygon,
  polygonFromAxisAlignedBounds,
} from '@backfield/ui/axisAlignedRectangle'
import type { LeafletFeatureCollections } from '@/lib/processedItemPlaceGeometry'
import {
  isPointGeometry,
  isPolygonGeometry,
} from '@/lib/processedItemPlaceGeometry'

const ADD_GEOMETRY_MAP_CENTER: [number, number] = [39.8283, -98.5795]
const ADD_GEOMETRY_MAP_ZOOM = 3

const EDIT_TILE = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'
const EDIT_ATTR =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'

function axisAlignedRectangleDraft(geometry: Record<string, unknown> | null): boolean {
  if (!isPolygonGeometry(geometry)) return false
  return isAxisAlignedRectanglePolygon(geometry)
}

export interface ProcessedItemVerificationLeafletMapProps {
  collections: LeafletFeatureCollections
  mapEditing: boolean
  geometryAddMode: 'point' | 'rectangle' | null
  onGeometryAddModeChange: (mode: 'point' | 'rectangle' | null) => void
  /** ``properties.id`` / feature id of the Point being edited (must exist in ``collections``). */
  editPointFeatureId: string | null
  /** Geometry for the selected place (merged view); updated by map edits. */
  draftGeometry: Record<string, unknown> | null
  onDraftGeometryChange: (g: Record<string, unknown> | null) => void
  onFeatureSelect?: (anchor: string) => void
  /** Map height in pixels (default 600 for verification layout). */
  mapHeightPx?: number
  /** When set, zoom the map to these bounds (see ``leafletBoundsFromGeometry``). */
  focusBounds?: [[number, number], [number, number]] | null
  /** Bump to re-fit when the same place is selected again. */
  focusBoundsKey?: number
}

export function ProcessedItemVerificationLeafletMap({
  collections,
  mapEditing,
  geometryAddMode,
  onGeometryAddModeChange,
  editPointFeatureId,
  draftGeometry,
  onDraftGeometryChange,
  onFeatureSelect,
  mapHeightPx = 600,
  focusBounds = null,
  focusBoundsKey = 0,
}: ProcessedItemVerificationLeafletMapProps) {
  const [rectanglePreview, setRectanglePreview] = useState<{
    southWest: { lat: number; lng: number }
    northEast: { lat: number; lng: number }
  } | null>(null)

  const leafletPoints = useMemo(() => collections.points as any, [collections.points])
  const leafletPolygons = useMemo(() => collections.polygons as any, [collections.polygons])

  return (
    <div className="h-full min-h-0 w-full overflow-hidden rounded-md bg-background">
      <LeafletMap
        height={mapHeightPx}
        points={leafletPoints}
        polygons={leafletPolygons}
        geocoder={mapEditing}
        showPopups={false}
        fitToData={!mapEditing && !focusBounds}
        focusBounds={focusBounds}
        focusBoundsKey={focusBoundsKey}
        initialCenter={
          mapEditing && !draftGeometry && (geometryAddMode === 'point' || geometryAddMode === 'rectangle')
            ? ADD_GEOMETRY_MAP_CENTER
            : null
        }
        initialZoom={
          mapEditing && !draftGeometry && (geometryAddMode === 'point' || geometryAddMode === 'rectangle')
            ? ADD_GEOMETRY_MAP_ZOOM
            : null
        }
        interactiveWhenEmpty={mapEditing && geometryAddMode === 'point' && !draftGeometry}
        tileUrl={mapEditing ? EDIT_TILE : undefined}
        tileAttribution={mapEditing ? EDIT_ATTR : undefined}
        onFeatureClick={
          onFeatureSelect
            ? (ev) => {
                const raw = ev.featureId ?? ''
                const anchor = raw.replace(/__baseline$|__draft$/, '')
                if (anchor) onFeatureSelect(anchor)
              }
            : undefined
        }
        onMapClick={
          mapEditing && geometryAddMode === 'point' && (!draftGeometry || isPointGeometry(draftGeometry))
            ? ({ latlng }) => {
                onDraftGeometryChange({ type: 'Point', coordinates: [latlng.lng, latlng.lat] })
                onGeometryAddModeChange(null)
              }
            : undefined
        }
        editablePoint={
          mapEditing &&
          editPointFeatureId &&
          isPointGeometry(draftGeometry) &&
          geometryAddMode !== 'rectangle'
            ? {
                featureId: editPointFeatureId,
                onChange: ({ lng, lat }) => {
                  onDraftGeometryChange({ type: 'Point', coordinates: [lng, lat] })
                },
              }
            : null
        }
        rectanglePreview={mapEditing ? rectanglePreview : null}
        editableRectangle={
          mapEditing &&
          isPolygonGeometry(draftGeometry) &&
          axisAlignedRectangleDraft(draftGeometry) &&
          geometryAddMode !== 'rectangle' &&
          boundsFromPolygonGeometry(draftGeometry as any)
            ? (() => {
                const b = boundsFromPolygonGeometry(draftGeometry as any)!
                return {
                  southWest: { lat: b.south, lng: b.west },
                  northEast: { lat: b.north, lng: b.east },
                  onChange: (next) => {
                    onDraftGeometryChange(
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
          mapEditing && geometryAddMode === 'rectangle'
            ? {
                enabled: true,
                onPreview: setRectanglePreview,
                onCommit: (bounds) => {
                  onDraftGeometryChange(
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
    </div>
  )
}
