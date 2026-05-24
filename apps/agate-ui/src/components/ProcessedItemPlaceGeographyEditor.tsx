import { isReviewOnlyMergedRow } from '@/lib/review/entities/location/reviewRow'
import { ProcessedItemVerificationLeafletMap } from '@/components/ProcessedItemVerificationLeafletMap'
import { GeocodedPlaceEditForm } from '@/components/GeocodedPlaceEditForm'
import { GeocodedPlacesTable } from '@/components/GeocodedPlacesTable'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import type { LeafletFeatureCollections } from '@/lib/review/entities/location/placeGeometry'
import type { PlaceEditFields } from '@/lib/review/entities/location/placeEditFields'
import { Loader2, Map, MousePointer, Pencil, Square, Trash2 } from 'lucide-react'

export interface ProcessedItemPlaceGeographyEditorProps {
  className?: string
  geometryEditing: boolean
  selectedAnchor: string | null
  mapDraftGeometry: Record<string, unknown> | null
  geometryAddMode: 'point' | 'rectangle' | null
  geometrySaving: boolean
  placeEditDirty: boolean
  placeFieldsDirty: boolean
  editPaneTab: 'map' | 'details'
  placeFieldsDraft: PlaceEditFields | undefined
  selectedOccurrenceClientId: string | null
  selectedRow: Record<string, unknown> | undefined
  mapCollections: LeafletFeatureCollections
  editPointFeatureId: string | null
  mapFocusBounds: [[number, number], [number, number]] | null
  mapFocusBoundsKey: number
  geocodedPlaceRows: Record<string, unknown>[]
  staleAnchorSet: Set<string>
  saving: boolean
  startGeometryEdit: () => void
  setGeometryAddMode: (mode: 'point' | 'rectangle' | null) => void
  clearGeometry: () => void
  cancelGeometryEdit: () => void
  saveGeometryForSelected: () => void
  setEditPaneTab: (tab: 'map' | 'details') => void
  onPlaceFieldsDraftChange: (fields: PlaceEditFields) => void
  onSelectedOccurrenceChange: (clientId: string) => void
  onMapGeometryChange: (geometry: Record<string, unknown> | null) => void
  onSelectAnchor: (anchor: string) => void
  getRowAnchor: (row: Record<string, unknown>) => string
  onOpenStylebookPlace: (row: Record<string, unknown>) => void
  onAdoptForStylebook: (row: Record<string, unknown>) => void
  onDeletePlace: (row: Record<string, unknown>) => void
  onShowAll: () => void
  onFindOnMap?: (row: Record<string, unknown>) => void
  cancelLabel?: string
}

const VERIFICATION_MAP_HEIGHT_PX = 300

export function ProcessedItemPlaceGeographyEditor({
  className,
  geometryEditing,
  selectedAnchor,
  mapDraftGeometry,
  geometryAddMode,
  geometrySaving,
  placeEditDirty,
  placeFieldsDirty,
  editPaneTab,
  placeFieldsDraft,
  selectedOccurrenceClientId,
  selectedRow,
  mapCollections,
  editPointFeatureId,
  mapFocusBounds,
  mapFocusBoundsKey,
  geocodedPlaceRows,
  staleAnchorSet,
  saving,
  startGeometryEdit,
  setGeometryAddMode,
  clearGeometry,
  cancelGeometryEdit,
  saveGeometryForSelected,
  setEditPaneTab,
  onPlaceFieldsDraftChange,
  onSelectedOccurrenceChange,
  onMapGeometryChange,
  onSelectAnchor,
  getRowAnchor,
  onOpenStylebookPlace,
  onAdoptForStylebook,
  onDeletePlace,
  onShowAll,
  onFindOnMap,
  cancelLabel = 'Cancel',
}: ProcessedItemPlaceGeographyEditorProps) {
  const mapActionsDisabled = saving || geometrySaving
  return (
    <div
      className={cn(
        'flex h-full min-h-0 min-w-0 flex-col gap-2 overflow-hidden rounded-lg border bg-card p-2.5',
        geometryEditing && 'border-primary/40 bg-background',
        className,
      )}
    >
      <div className="flex w-full shrink-0 flex-wrap items-center gap-2">
        {selectedAnchor && !geometryEditing ? (
          <>
            <Button
              type="button"
              size="sm"
              className="bg-black text-white hover:bg-black/90"
              disabled={mapActionsDisabled}
              onClick={startGeometryEdit}
            >
              <Pencil className="mr-2 h-4 w-4" />
              Edit
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={mapActionsDisabled || !selectedRow}
              onClick={() => {
                if (selectedRow) onDeletePlace(selectedRow)
              }}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={mapActionsDisabled}
              onClick={onShowAll}
            >
              <Map className="mr-2 h-4 w-4" />
              Show all
            </Button>
          </>
        ) : null}
        {geometryEditing && !mapDraftGeometry ? (
          <>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={geometryAddMode === 'rectangle' || geometrySaving}
              onClick={() => setGeometryAddMode('point')}
            >
              <MousePointer className="mr-2 h-4 w-4" />
              Add point
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={geometryAddMode === 'point' || geometrySaving}
              onClick={() => setGeometryAddMode('rectangle')}
            >
              <Square className="mr-2 h-4 w-4" />
              Add rectangle
            </Button>
          </>
        ) : null}
        {geometryEditing && mapDraftGeometry ? (
          <Button
            type="button"
            variant="destructive"
            size="sm"
            disabled={geometrySaving}
            onClick={clearGeometry}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Clear geography
          </Button>
        ) : null}
        {geometryEditing && selectedAnchor ? (
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={geometrySaving}
              onClick={cancelGeometryEdit}
            >
              {cancelLabel}
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={!placeEditDirty || geometrySaving}
              onClick={saveGeometryForSelected}
            >
              {geometrySaving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving…
                </>
              ) : (
                'Save'
              )}
            </Button>
          </div>
        ) : null}
      </div>
      {geometryEditing ? (
        <Tabs
          value={editPaneTab}
          onValueChange={(v) => setEditPaneTab(v === 'details' ? 'details' : 'map')}
          className="flex min-h-0 min-w-0 flex-1 flex-col"
        >
          <TabsList className="h-9 w-full shrink-0 justify-start">
            <TabsTrigger value="map" className="flex-1 sm:flex-none">
              Map
            </TabsTrigger>
            <TabsTrigger value="details" className="flex-1 sm:flex-none">
              Place details
              {placeFieldsDirty ? (
                <span className="ml-1.5 text-primary" aria-hidden>
                  •
                </span>
              ) : null}
            </TabsTrigger>
          </TabsList>
          <div className="relative mt-2 min-h-0 flex-1">
            <TabsContent
              value="map"
              className="absolute inset-0 mt-0 flex flex-col gap-2 overflow-hidden focus-visible:outline-none data-[state=inactive]:hidden"
            >
              <div className="relative z-0 flex min-h-0 flex-1 flex-col overflow-hidden rounded-md bg-background">
                <ProcessedItemVerificationLeafletMap
                  collections={mapCollections}
                  mapEditing={geometryEditing}
                  geometryAddMode={geometryAddMode}
                  onGeometryAddModeChange={setGeometryAddMode}
                  editPointFeatureId={editPointFeatureId}
                  draftGeometry={mapDraftGeometry}
                  onDraftGeometryChange={onMapGeometryChange}
                  mapHeightPx={VERIFICATION_MAP_HEIGHT_PX}
                  mapFillHeight
                  focusBounds={mapFocusBounds}
                  focusBoundsKey={mapFocusBoundsKey}
                  onFeatureSelect={onSelectAnchor}
                />
              </div>
              {geometryAddMode === 'rectangle' ? (
                <p className="shrink-0 text-xs text-muted-foreground">
                  Hold Shift and drag on the map to draw an area.
                </p>
              ) : selectedRow && isReviewOnlyMergedRow(selectedRow) ? (
                <p className="shrink-0 text-xs text-muted-foreground">
                  These changes are saved with this review only until the place is saved for this story.
                </p>
              ) : null}
            </TabsContent>
            <TabsContent
              value="details"
              className="absolute inset-0 mt-0 overflow-y-auto p-1.5 focus-visible:outline-none data-[state=inactive]:hidden"
            >
              {placeFieldsDraft ? (
                <GeocodedPlaceEditForm
                  embeddedInTab
                  fields={placeFieldsDraft}
                  disabled={geometrySaving}
                  selectedOccurrenceClientId={selectedOccurrenceClientId}
                  onSelectOccurrence={onSelectedOccurrenceChange}
                  onChange={onPlaceFieldsDraftChange}
                />
              ) : null}
            </TabsContent>
          </div>
        </Tabs>
      ) : (
        <div className="relative z-0 w-full shrink-0 overflow-hidden rounded-md bg-background">
          <ProcessedItemVerificationLeafletMap
            collections={mapCollections}
            mapEditing={false}
            geometryAddMode={geometryAddMode}
            onGeometryAddModeChange={setGeometryAddMode}
            editPointFeatureId={editPointFeatureId}
            draftGeometry={mapDraftGeometry}
            onDraftGeometryChange={onMapGeometryChange}
            mapHeightPx={VERIFICATION_MAP_HEIGHT_PX}
            mapFillHeight={false}
            focusBounds={mapFocusBounds}
            focusBoundsKey={mapFocusBoundsKey}
            onFeatureSelect={onSelectAnchor}
          />
        </div>
      )}

      {!geometryEditing ? (
        <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-1 overflow-hidden border-t border-border pt-2">
          <h4 className="shrink-0 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Geocoded places
          </h4>
          <GeocodedPlacesTable
            rows={geocodedPlaceRows}
            selectedAnchor={selectedAnchor}
            staleAnchorSet={staleAnchorSet}
            getRowAnchor={getRowAnchor}
            onSelectAnchor={onSelectAnchor}
            onOpenStylebookPlace={onOpenStylebookPlace}
            onAdoptForStylebook={onAdoptForStylebook}
            adoptDisabled={saving || geometrySaving}
            onDeletePlace={onDeletePlace}
            deleteDisabled={saving || geometrySaving}
            onFindOnMap={onFindOnMap}
          />
        </div>
      ) : null}
    </div>
  )
}
