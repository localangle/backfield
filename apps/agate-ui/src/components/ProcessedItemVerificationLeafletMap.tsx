import { GeometryEditLeafletMap } from '@backfield/ui/GeometryEditLeafletMap'
import type { LeafletFeatureCollections } from '@/lib/review/entities/location/placeGeometry'

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
  /** Map height in pixels (default matches verification Review layout). */
  mapHeightPx?: number
  /** When true, map fills the parent flex area (edit mode). */
  mapFillHeight?: boolean
  /** When set, zoom the map to these bounds once per selection (``focusBoundsKey``). */
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
  mapHeightPx = 360,
  mapFillHeight = false,
  focusBounds = null,
  focusBoundsKey = 0,
}: ProcessedItemVerificationLeafletMapProps) {
  return (
    <div className="h-full min-h-0 w-full overflow-hidden bg-background">
      <GeometryEditLeafletMap
        height={mapHeightPx}
        fillHeight={mapFillHeight}
        points={collections.points as any}
        polygons={collections.polygons as any}
        geometryEditing={mapEditing}
        geometryDraft={draftGeometry}
        onGeometryDraftChange={onDraftGeometryChange}
        geometryAddMode={geometryAddMode}
        onGeometryAddModeChange={onGeometryAddModeChange}
        editPointFeatureId={editPointFeatureId}
        focusBounds={focusBounds}
        focusBoundsKey={focusBoundsKey}
        onFeatureClick={
          onFeatureSelect
            ? (ev) => {
                const raw = ev.featureId ?? ''
                const anchor = raw.replace(/__baseline$|__draft$/, '')
                if (anchor) onFeatureSelect(anchor)
              }
            : undefined
        }
      />
    </div>
  )
}
