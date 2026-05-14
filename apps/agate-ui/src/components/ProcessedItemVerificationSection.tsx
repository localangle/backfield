import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { LeafletMap } from '@backfield/ui/LeafletMap'
import { useAppMessage } from '@/components/AppMessageProvider'
import { ProcessedItemArticleBody } from '@/components/ProcessedItemArticleBody'
import { ProcessedItemVerificationLeafletMap } from '@/components/ProcessedItemVerificationLeafletMap'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import type { Graph, ProcessedItem } from '@/lib/api'
import { getProcessedItem, patchProcessedItemOverlay } from '@/lib/api'
import {
  applyAnchorPatchFragment,
  appendUserPlacePoint,
  buildGeocodePatchForGeometry,
  buildVerificationLeafletCollections,
  extractGeometryFromPlace,
  isApiOverlayGeometryError,
  iterBaselinePlacesFromOutput,
  shallowMergePlacePatch,
  validateGeometryObject,
} from '@/lib/processedItemPlaceGeometry'
import { resolveEvidenceSpanInArticle } from '@/lib/processedItemEvidenceSpan'
import {
  applyDescriptionPatch,
  getLocationDescription,
  getMergedRowAnchor,
  isApiConflictError,
  isLocationLinkedToStylebookCanonical,
  normalizeOverlay,
  overlaysStructurallyEqual,
} from '@/lib/processedItemVerificationOverlay'
import { Loader2, MapPin, MousePointer, Square } from 'lucide-react'

function nodeLabelForId(graph: Graph | null, nodeId: string): string {
  const n = graph?.spec?.nodes?.find((x) => x.id === nodeId)
  if (!n) return nodeId
  const p = n.params as Record<string, unknown> | undefined
  const name = p?.name ?? p?.label
  return typeof name === 'string' && name.trim() ? name : n.type
}

export interface ProcessedItemVerificationSectionProps {
  runId: string
  item: ProcessedItem
  graph: Graph | null
  onItemUpdated: (item: ProcessedItem) => void
  /** Fires when overlay draft dirty state changes (for navigation guard with ``BrowserRouter``). */
  onVerificationDirtyChange?: (dirty: boolean) => void
}

export function ProcessedItemVerificationSection({
  runId,
  item,
  graph,
  onItemUpdated,
  onVerificationDirtyChange,
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
  const [hoveredAnchor, setHoveredAnchor] = useState<string | null>(null)
  const [geometryAddMode, setGeometryAddMode] = useState<'point' | 'rectangle' | null>(null)

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

  const storyHighlightAnchor = hoveredAnchor ?? selectedAnchor

  const storyHighlightResult = useMemo(() => {
    const body = typeof article?.body === 'string' ? article.body : ''
    if (!storyHighlightAnchor) {
      return resolveEvidenceSpanInArticle(body, undefined)
    }
    const row = mergedRows.find((r) => getMergedRowAnchor(r) === storyHighlightAnchor)
    if (!row) {
      return resolveEvidenceSpanInArticle(body, undefined)
    }
    const loc =
      row.source === 'model'
        ? (baselineByAnchor.get(storyHighlightAnchor) ?? null)
        : ((previewMergedRows.find((r) => getMergedRowAnchor(r) === storyHighlightAnchor)?.location ??
            null) as Record<string, unknown> | null)
    return resolveEvidenceSpanInArticle(body, loc ?? undefined)
  }, [article?.body, storyHighlightAnchor, mergedRows, previewMergedRows, baselineByAnchor])

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

  const handleDescriptionChange = useCallback((anchor: string, value: string) => {
    setDraftOverlay((prev) => {
      const next = normalizeOverlay(prev)
      applyDescriptionPatch(next, anchor, value)
      return next
    })
  }, [])

  const handleSave = useCallback(async () => {
    if (!dirty || saving) return
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

  const handleStylebookHandoff = useCallback(async () => {
    if (dirty) {
      const leave = await showConfirm(
        'Save your changes before opening the catalog, or stay here to keep editing.',
        {
          title: 'Unsaved changes',
          confirmLabel: 'Continue without saving',
          cancelLabel: 'Stay',
          destructive: true,
        },
      )
      if (!leave) {
        return
      }
    }
    showMessage(
      'Opening your catalog from this screen will arrive in a later update. For now, use your catalog workspace in another tab if you need to edit the linked entry.',
      { title: 'Catalog' },
    )
  }, [dirty, showConfirm, showMessage])

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
            Compare the story text with extracted places. Linked catalog entries can only be edited in
            your catalog.
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

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-2 min-h-[12rem]">
            <h3 className="text-sm font-semibold">Story text</h3>
            {article?.headline ? (
              <p className="text-sm font-medium text-foreground">{article.headline}</p>
            ) : null}
            {article?.resolution === 'none' && !article.body.trim() ? (
              <p className="text-sm text-muted-foreground">
                No article text is available for this item yet.
              </p>
            ) : (
              <div className="rounded-md border bg-muted/30 p-3 max-h-[min(70vh,36rem)] overflow-y-auto">
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

          <div className="space-y-2 min-h-[12rem]">
            <h3 className="text-sm font-semibold">Places</h3>
            {mergedRows.length === 0 ? (
              <p className="text-sm text-muted-foreground">No extracted places are listed for this item.</p>
            ) : (
              <ul className="space-y-3 max-h-[min(70vh,36rem)] overflow-y-auto pr-1">
                {mergedRows.map((row, idx) => {
                  const anchor = getMergedRowAnchor(row)
                  const loc = row.location as Record<string, unknown> | undefined
                  const baselineLoc =
                    row.source === 'model' && anchor ? baselineByAnchor.get(anchor) : undefined
                  const modelFlaggedReview =
                    row.source === 'model' &&
                    baselineLoc !== undefined &&
                    typeof baselineLoc === 'object' &&
                    baselineLoc !== null &&
                    (baselineLoc as { needs_review?: unknown }).needs_review === true
                  const rowStale = row.stale === true || (anchor ? staleAnchorSet.has(anchor) : false)
                  const linked = isLocationLinkedToStylebookCanonical(loc)
                  const source = row.source === 'user' ? 'Added by you' : 'From model'
                  const nodeId = typeof row.node_id === 'string' ? row.node_id : ''
                  const nodeLabel = nodeId ? nodeLabelForId(graph, nodeId) : ''
                  const description = getLocationDescription(loc)
                  const displayDescription =
                    typeof description === 'string' && description.length > 0 ? description : ''

                  const by = (draftOverlay.locations as Record<string, unknown> | undefined)?.by_anchor as
                    | Record<string, unknown>
                    | undefined
                  const patch = by?.[anchor] as Record<string, unknown> | undefined
                  const inputValue =
                    patch && typeof patch.description === 'string' ? patch.description : displayDescription

                  return (
                    <li
                      key={anchor || `row-${idx}`}
                      className="rounded-md border p-3 space-y-2 bg-card cursor-pointer"
                      onMouseEnter={() => {
                        if (anchor) setHoveredAnchor(anchor)
                      }}
                      onMouseLeave={() => {
                        setHoveredAnchor((h) => (h === anchor ? null : h))
                      }}
                      onClick={(e) => {
                        const t = e.target as HTMLElement
                        if (t.closest('button, input, textarea, a, label')) return
                        if (!anchor) return
                        setSelectedAnchor(anchor)
                        setGeometryAddMode(null)
                      }}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="secondary">{source}</Badge>
                        {nodeLabel ? (
                          <span className="text-xs text-muted-foreground truncate max-w-[12rem]">
                            {nodeLabel}
                          </span>
                        ) : null}
                        {modelFlaggedReview ? (
                          <Badge variant="outline" className="border-amber-300 text-amber-900 dark:text-amber-100">
                            Flagged by the model
                          </Badge>
                        ) : null}
                        {rowStale ? (
                          <Badge variant="outline" className="text-amber-800 border-amber-300">
                            Saved edit may not apply
                          </Badge>
                        ) : null}
                        <Button
                          type="button"
                          variant={selectedAnchor === anchor ? 'default' : 'outline'}
                          size="sm"
                          className="ml-auto"
                          onClick={(ev) => {
                            ev.stopPropagation()
                            setSelectedAnchor(anchor)
                            setMapEditing(true)
                            setGeometryAddMode(null)
                          }}
                        >
                          On map
                        </Button>
                      </div>
                      {linked ? (
                        <>
                          <p className="text-sm text-foreground">{displayDescription || '—'}</p>
                          <p className="text-xs text-muted-foreground">
                            This place is linked to your catalog. Map edits here stay with this run as
                            drafts until you promote them in your catalog.
                          </p>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="w-full sm:w-auto"
                            disabled
                            title="Coming soon"
                          >
                            Edit in catalog
                          </Button>
                        </>
                      ) : (
                        <div className="space-y-1">
                          <label className="text-xs font-medium text-muted-foreground" htmlFor={`desc-${anchor}`}>
                            Description
                          </label>
                          <Input
                            id={`desc-${anchor}`}
                            value={inputValue}
                            onChange={(ev) => handleDescriptionChange(anchor, ev.target.value)}
                            disabled={!anchor}
                          />
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold inline-flex items-center gap-2">
              <MapPin className="h-4 w-4" aria-hidden />
              Map
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
          {geometryAddMode === 'point' && selectedAnchor === null ? (
            <LeafletMap
              points={mapCollections.points as any}
              polygons={mapCollections.polygons as any}
              geocoder
              showPopups={false}
              fitToData={false}
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
              onFeatureSelect={(anchor) => {
                setSelectedAnchor(anchor)
                setMapEditing(true)
                setGeometryAddMode(null)
              }}
            />
          )}
        </div>
      </CardContent>
    </Card>
  )
}
