import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { LeafletMap } from '@backfield/ui/LeafletMap'
import { useAppMessage } from '@/components/AppMessageProvider'
import { ProcessedItemArticleBody } from '@/components/ProcessedItemArticleBody'
import { ProcessedItemVerificationLeafletMap } from '@/components/ProcessedItemVerificationLeafletMap'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { Graph, ProcessedItem } from '@/lib/api'
import { getProcessedItem, patchProcessedItemOverlay } from '@/lib/api'
import { stylebookCanonicalDetailHref, stylebookCanonicalListHref } from '@/lib/platformUrls'
import {
  applyAnchorPatchFragment,
  appendUserPlacePoint,
  buildGeocodePatchForGeometry,
  buildVerificationLeafletCollections,
  extractGeometryFromPlace,
  getGeocodedPlaceDisplay,
  isApiOverlayGeometryError,
  isGeocodedPlace,
  iterBaselinePlacesFromOutput,
  leafletBoundsFromGeometry,
  shallowMergePlacePatch,
  validateGeometryObject,
} from '@/lib/processedItemPlaceGeometry'
import { resolveEvidenceSpanInArticle } from '@/lib/processedItemEvidenceSpan'
import {
  getLocationDescription,
  getMergedRowAnchor,
  getStylebookCanonicalHandoffId,
  isApiConflictError,
  normalizeOverlay,
  overlaysStructurallyEqual,
} from '@/lib/processedItemVerificationOverlay'
import { Loader2, MapPin, MousePointer, Square } from 'lucide-react'

function formatPlaceFieldLabel(raw: string): string {
  const t = raw.trim()
  if (!t) return '—'
  return t.replace(/_/g, ' ')
}

export interface ProcessedItemVerificationSectionProps {
  runId: string
  item: ProcessedItem
  graph: Graph | null
  onItemUpdated: (item: ProcessedItem) => void
  /** Fires when overlay draft dirty state changes (for navigation guard with ``BrowserRouter``). */
  onVerificationDirtyChange?: (dirty: boolean) => void
  /** Catalog slug from the run's project workspace (for opening Stylebook). */
  catalogStylebookSlug?: string | null
  /** Agate project slug for Stylebook ``?project=`` context. */
  catalogProjectSlug?: string | null
}

export function ProcessedItemVerificationSection({
  runId,
  item,
  graph,
  onItemUpdated,
  onVerificationDirtyChange,
  catalogStylebookSlug = null,
  catalogProjectSlug = null,
}: ProcessedItemVerificationSectionProps) {
  const { showError, showConfirm, showMessage } = useAppMessage()
  const [baselineOverlay, setBaselineOverlay] = useState<Record<string, unknown>>(() =>
    normalizeOverlay(item.overlay),
  )
  const [draftOverlay, setDraftOverlay] = useState<Record<string, unknown>>(() =>
    normalizeOverlay(item.overlay),
  )
  const [saving, setSaving] = useState(false)
  const lastItemSyncKeyRef = useRef<string>('')

  const [mapEditing, setMapEditing] = useState(false)
  const [selectedAnchor, setSelectedAnchor] = useState<string | null>(null)
  const [geometryAddMode, setGeometryAddMode] = useState<'point' | 'rectangle' | null>(null)
  const [mapFocusBoundsKey, setMapFocusBoundsKey] = useState(0)

  const dirty = useMemo(
    () => !overlaysStructurallyEqual(baselineOverlay, draftOverlay),
    [baselineOverlay, draftOverlay],
  )

  useEffect(() => {
    onVerificationDirtyChange?.(dirty)
  }, [dirty, onVerificationDirtyChange])

  const syncKey = `${runId}:${item.id}:${item.overlay_version}`

  useEffect(() => {
    if (lastItemSyncKeyRef.current !== syncKey) {
      lastItemSyncKeyRef.current = syncKey
      const n = normalizeOverlay(item.overlay)
      setBaselineOverlay(n)
      setDraftOverlay(n)
      return
    }
    if (!dirty) {
      const n = normalizeOverlay(item.overlay)
      setBaselineOverlay(n)
      setDraftOverlay(n)
    }
  }, [item.overlay, item.overlay_version, item.id, runId, syncKey, dirty])

  useEffect(() => {
    if (!dirty) {
      return
    }
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [dirty])

  const mergedRows = item.merged_locations ?? []
  const staleEntries = item.stale_overlay_entries ?? []
  const staleAnchorSet = useMemo(() => {
    const s = new Set<string>()
    for (const e of staleEntries) {
      const a = typeof (e as { anchor?: unknown }).anchor === 'string' ? (e as { anchor: string }).anchor : ''
      if (a) s.add(a)
    }
    return s
  }, [staleEntries])
  const article = item.article_context

  const baselineByAnchor = useMemo(() => {
    const m = new Map<string, Record<string, unknown>>()
    const out = (item.output ?? null) as Record<string, unknown> | null
    for (const row of iterBaselinePlacesFromOutput(out)) {
      m.set(row.anchor, row.location)
    }
    return m
  }, [item.output])

  const previewMergedRows = useMemo(() => {
    const by = ((draftOverlay.locations as Record<string, unknown> | undefined)?.by_anchor ?? {}) as Record<
      string,
      unknown
    >
    return mergedRows.map((row) => {
      const anchor = getMergedRowAnchor(row)
      const patch = by[anchor] as Record<string, unknown> | undefined
      const loc = row.location as Record<string, unknown> | undefined
      if (!loc || !patch) return row
      return {
        ...row,
        location: shallowMergePlacePatch(loc, patch),
      }
    })
  }, [mergedRows, draftOverlay])

  const storyHighlightAnchor = selectedAnchor

  const geocodedPlaceRows = useMemo(
    () =>
      previewMergedRows.filter((row) => {
        const loc = row.location as Record<string, unknown> | undefined
        return isGeocodedPlace(loc)
      }),
    [previewMergedRows],
  )

  const mapFocusBounds = useMemo(() => {
    if (!selectedAnchor) return null
    const row = previewMergedRows.find((r) => getMergedRowAnchor(r) === selectedAnchor)
    const loc = row?.location as Record<string, unknown> | undefined
    return leafletBoundsFromGeometry(extractGeometryFromPlace(loc ?? null))
  }, [previewMergedRows, selectedAnchor])

  const selectPlaceAnchor = useCallback((anchor: string) => {
    setSelectedAnchor(anchor)
    setMapFocusBoundsKey((k) => k + 1)
    setGeometryAddMode(null)
  }, [])

  const storyHighlightResult = useMemo(() => {
    const body = typeof article?.body === 'string' ? article.body : ''
    if (!storyHighlightAnchor) {
      return resolveEvidenceSpanInArticle(body, undefined)
    }
    const row = previewMergedRows.find((r) => getMergedRowAnchor(r) === storyHighlightAnchor)
    const loc = (row?.location ?? null) as Record<string, unknown> | null
    return resolveEvidenceSpanInArticle(body, loc ?? undefined)
  }, [article?.body, storyHighlightAnchor, previewMergedRows])

  const storyHighlightRange = storyHighlightResult.kind === 'range' ? storyHighlightResult : null

  const mapCollections = useMemo(
    () =>
      buildVerificationLeafletCollections({
        mergedRows: previewMergedRows,
        baselineByAnchor,
        selectedAnchor,
      }),
    [previewMergedRows, baselineByAnchor, selectedAnchor],
  )

  const editPointFeatureId = useMemo(() => {
    if (!selectedAnchor) return null
    const pts = mapCollections.points.features as Array<{ properties?: { id?: string } }>
    const draftId = `${selectedAnchor}__draft`
    if (pts.some((f) => f.properties?.id === draftId)) return draftId
    if (pts.some((f) => f.properties?.id === selectedAnchor)) return selectedAnchor
    return null
  }, [mapCollections.points.features, selectedAnchor])

  const mapDraftGeometry = useMemo(() => {
    if (!selectedAnchor) return null
    const row = previewMergedRows.find((r) => getMergedRowAnchor(r) === selectedAnchor)
    const loc = row?.location as Record<string, unknown> | undefined
    return extractGeometryFromPlace(loc ?? null)
  }, [previewMergedRows, selectedAnchor])

  const handleMapGeometryChange = useCallback(
    (g: Record<string, unknown> | null) => {
      if (!selectedAnchor || !g) return
      const err = validateGeometryObject(g)
      if (err) {
        showError(err, { title: 'Map' })
        return
      }
      setDraftOverlay((prev) => {
        const next = normalizeOverlay(prev)
        const row = mergedRows.find((r) => getMergedRowAnchor(r) === selectedAnchor)
        const base = (row?.location as Record<string, unknown> | undefined) ?? {}
        const by = ((prev.locations as Record<string, unknown> | undefined)?.by_anchor ?? {}) as Record<
          string,
          unknown
        >
        const mergedBase = shallowMergePlacePatch(base, by[selectedAnchor] as Record<string, unknown> | undefined)
        const fragment = buildGeocodePatchForGeometry(mergedBase, g)
        applyAnchorPatchFragment(next, selectedAnchor, fragment)
        return next
      })
    },
    [selectedAnchor, mergedRows, showError],
  )

  const persistOverlayDraft = useCallback(async (): Promise<boolean> => {
    if (!dirty) {
      return true
    }
    if (saving) {
      return false
    }
    setSaving(true)
    try {
      const updated = await patchProcessedItemOverlay(
        runId,
        item.id,
        draftOverlay,
        item.overlay_version ?? 0,
      )
      onItemUpdated(updated)
      const n = normalizeOverlay(updated.overlay)
      setBaselineOverlay(n)
      setDraftOverlay(n)
      return true
    } catch (e) {
      if (isApiConflictError(e)) {
        showError(
          'Someone else saved changes to this item while you were editing. This page has been refreshed with the latest version.',
          { title: 'Could not save' },
        )
        try {
          const fresh = await getProcessedItem(runId, item.id)
          onItemUpdated(fresh)
          const n = normalizeOverlay(fresh.overlay)
          setBaselineOverlay(n)
          setDraftOverlay(n)
        } catch {
          showError('We could not reload this item. Try opening it again from the run.', {
            title: 'Reload failed',
          })
        }
      } else if (isApiOverlayGeometryError(e)) {
        showError(
          'The map shape could not be saved. Try simplifying the area or moving the pin slightly, then save again.',
          { title: 'Could not save map' },
        )
      } else {
        showError('We could not save your changes. Check your connection and try again.', {
          title: 'Save failed',
        })
      }
      return false
    } finally {
      setSaving(false)
    }
  }, [
    dirty,
    saving,
    runId,
    item.id,
    item.overlay_version,
    draftOverlay,
    onItemUpdated,
    showError,
  ])

  const handleSave = useCallback(async () => {
    if (!dirty || saving) {
      return
    }
    await persistOverlayDraft()
  }, [dirty, saving, persistOverlayDraft])

  const handleStylebookHandoff = useCallback(async () => {
    const slug = typeof catalogStylebookSlug === 'string' && catalogStylebookSlug.trim() ? catalogStylebookSlug.trim() : ''
    if (!slug) {
      showMessage(
        'This project’s workspace does not have a catalog linked yet. An administrator can link a catalog to the workspace so you can open it from here.',
        { title: 'Catalog' },
      )
      return
    }
    if (dirty) {
      const saveAndOpen = await showConfirm(
        'Save your review changes first. After they are saved, your catalog opens in a new browser tab.',
        {
          title: 'Save before opening catalog',
          confirmLabel: 'Save and open catalog',
          cancelLabel: 'Stay',
          destructive: false,
        },
      )
      if (!saveAndOpen) {
        return
      }
      const saved = await persistOverlayDraft()
      if (!saved) {
        return
      }
    }
    const proj = typeof catalogProjectSlug === 'string' && catalogProjectSlug.trim() ? catalogProjectSlug.trim() : null
    const row = selectedAnchor
      ? previewMergedRows.find((r) => getMergedRowAnchor(r) === selectedAnchor)
      : undefined
    const loc = row?.location as Record<string, unknown> | undefined
    const canonicalId = getStylebookCanonicalHandoffId(loc)
    const searchHint = getLocationDescription(loc).trim().slice(0, 200)
    const url = canonicalId
      ? stylebookCanonicalDetailHref(slug, canonicalId, proj)
      : stylebookCanonicalListHref(slug, { projectSlug: proj, searchQuery: searchHint || null })
    window.open(url, '_blank', 'noopener,noreferrer')
  }, [
    catalogProjectSlug,
    catalogStylebookSlug,
    dirty,
    persistOverlayDraft,
    previewMergedRows,
    selectedAnchor,
    showConfirm,
    showMessage,
  ])

  const handleAddNewPointMode = useCallback(() => {
    setGeometryAddMode('point')
    setSelectedAnchor(null)
    setMapEditing(true)
  }, [])

  const handleMapClickForNewPlace = useCallback(
    ({ latlng }: { latlng: { lat: number; lng: number } }) => {
      if (geometryAddMode !== 'point' || selectedAnchor !== null) return
      setDraftOverlay((prev) => {
        const next = normalizeOverlay(prev)
        const id = appendUserPlacePoint(next, latlng.lng, latlng.lat, 'New place')
        requestAnimationFrame(() => {
          setSelectedAnchor(id)
          setGeometryAddMode(null)
        })
        return next
      })
    },
    [geometryAddMode, selectedAnchor],
  )

  return (
    <Card className="border-primary/30">
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <CardTitle>Review</CardTitle>
          <CardDescription>
            Read the story beside the map. Pick a geocoded place below to highlight it in the story
            and zoom the map. Use Edit map to adjust locations, then save when you are ready.
          </CardDescription>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => void handleStylebookHandoff()}>
            Open catalog
          </Button>
          <Button type="button" size="sm" disabled={!dirty || saving} onClick={() => void handleSave()}>
            {saving ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving…
              </>
            ) : (
              'Save changes'
            )}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {staleEntries.length > 0 ? (
          <Alert
            variant="default"
            className="border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-50"
          >
            <AlertDescription>
              Some of your saved edits no longer match this run’s model output. They are kept on file
              but may not apply until you review them against the latest extraction.
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
          <div className="flex min-h-0 flex-col space-y-2 lg:min-h-[min(70vh,40rem)]">
            <h3 className="text-sm font-semibold">Story text</h3>
            {article?.headline ? (
              <p className="text-sm font-medium text-foreground">{article.headline}</p>
            ) : null}
            {article?.resolution === 'none' && !article.body.trim() ? (
              <p className="text-sm text-muted-foreground">
                No article text is available for this item yet.
              </p>
            ) : (
              <div className="min-h-0 flex-1 overflow-y-auto rounded-md border bg-muted/30 p-3">
                {article?.body?.trim() ? (
                  <>
                    <ProcessedItemArticleBody
                      body={article.body}
                      highlight={storyHighlightRange}
                      scrollWhenKey={selectedAnchor}
                    />
                    {storyHighlightAnchor &&
                    storyHighlightResult.kind === 'none' &&
                    article.body.trim().length > 0 ? (
                      <p className="mt-2 text-xs text-muted-foreground border-t border-border/60 pt-2">
                        No matching passage was found in this story for this place.
                      </p>
                    ) : null}
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">No story text is available for this item yet.</p>
                )}
              </div>
            )}
            {article?.resolution === 'inline_fallback' ? (
              <p className="text-xs text-muted-foreground">
                Showing text saved with this run when a full article could not be loaded.
              </p>
            ) : null}
          </div>

          <div
            className={
              mapEditing
                ? 'flex min-h-0 flex-col gap-3 rounded-lg border border-primary/30 bg-primary/[0.06] p-3 ring-2 ring-primary/20 dark:bg-primary/10'
                : 'flex min-h-0 flex-col gap-3 rounded-lg border bg-card p-3'
            }
          >
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold inline-flex items-center gap-2">
                <MapPin className="h-4 w-4" aria-hidden />
                Locations map
              </h3>
              <Button
                type="button"
                variant={mapEditing ? 'secondary' : 'outline'}
                size="sm"
                onClick={() => {
                  setMapEditing((v) => !v)
                  if (mapEditing) {
                    setGeometryAddMode(null)
                  }
                }}
              >
                {mapEditing ? 'Done editing map' : 'Edit map'}
              </Button>
              {mapEditing ? (
                <>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={geometryAddMode === 'rectangle'}
                    onClick={() => {
                      setGeometryAddMode('point')
                    }}
                  >
                    <MousePointer className="mr-2 h-4 w-4" />
                    Add point
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={geometryAddMode === 'point'}
                    onClick={() => {
                      setGeometryAddMode('rectangle')
                    }}
                  >
                    <Square className="mr-2 h-4 w-4" />
                    Add rectangle
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      void handleAddNewPointMode()
                    }}
                  >
                    New place (point)
                  </Button>
                </>
              ) : null}
            </div>
            <p className="text-xs text-muted-foreground">
              Same map tools as catalog location pages: pick a place with On map, then drag the pin or
              draw a rectangle. Save when you are ready; changes are not shared until you save.
            </p>
            <div className="min-h-[min(45vh,22rem)] w-full shrink-0 lg:min-h-[560px]">
              {geometryAddMode === 'point' && selectedAnchor === null ? (
                <LeafletMap
                  points={mapCollections.points as any}
                  polygons={mapCollections.polygons as any}
                  geocoder
                  showPopups={false}
                  fitToData={false}
                  height={600}
                  initialCenter={[39.8283, -98.5795]}
                  initialZoom={3}
                  interactiveWhenEmpty
                  tileUrl="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
                  tileAttribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
                  onMapClick={(e) => handleMapClickForNewPlace(e)}
                />
              ) : (
                <ProcessedItemVerificationLeafletMap
                  collections={mapCollections}
                  mapEditing={mapEditing}
                  geometryAddMode={geometryAddMode}
                  onGeometryAddModeChange={setGeometryAddMode}
                  editPointFeatureId={editPointFeatureId}
                  draftGeometry={mapDraftGeometry}
                  onDraftGeometryChange={handleMapGeometryChange}
                  mapHeightPx={600}
                  focusBounds={mapFocusBounds}
                  focusBoundsKey={mapFocusBoundsKey}
                  onFeatureSelect={(anchor) => {
                    selectPlaceAnchor(anchor)
                  }}
                />
              )}
            </div>

            <div className="min-h-0 space-y-2 border-t border-border pt-3">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Geocoded places
              </h4>
              {geocodedPlaceRows.length === 0 ? (
                <p className="text-sm text-muted-foreground">No geocoded places are listed for this item yet.</p>
              ) : (
                <ul className="max-h-[min(38vh,20rem)] space-y-2 overflow-y-auto pr-1">
                  {geocodedPlaceRows.map((row, idx) => {
                    const anchor = getMergedRowAnchor(row)
                    const loc = row.location as Record<string, unknown> | undefined
                    const display = getGeocodedPlaceDisplay(loc)
                    const selected = selectedAnchor === anchor
                    const rowStale = row.stale === true || (anchor ? staleAnchorSet.has(anchor) : false)

                    return (
                      <li
                        key={anchor || `geo-${idx}`}
                        role="button"
                        tabIndex={0}
                        className={
                          selected
                            ? 'cursor-pointer space-y-1.5 rounded-md border border-primary bg-primary/5 p-2.5 ring-1 ring-primary/30'
                            : 'cursor-pointer space-y-1.5 rounded-md border bg-background p-2.5 hover:bg-muted/40'
                        }
                        onClick={() => {
                          if (anchor) selectPlaceAnchor(anchor)
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            if (anchor) selectPlaceAnchor(anchor)
                          }
                        }}
                      >
                        <p className="text-sm font-medium leading-snug text-foreground">
                          {display.name || '—'}
                        </p>
                        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                          <dt className="font-medium text-foreground/80">Type</dt>
                          <dd>{formatPlaceFieldLabel(display.type)}</dd>
                          <dt className="font-medium text-foreground/80">Address</dt>
                          <dd className="text-foreground/90">{display.formattedAddress || '—'}</dd>
                          <dt className="font-medium text-foreground/80">Role</dt>
                          <dd>{formatPlaceFieldLabel(display.role)}</dd>
                        </dl>
                        {rowStale ? (
                          <Badge variant="outline" className="mt-1 border-amber-300 text-amber-800">
                            Saved edit may not apply
                          </Badge>
                        ) : null}
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
