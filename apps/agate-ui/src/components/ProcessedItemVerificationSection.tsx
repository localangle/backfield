import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { isAxisAlignedRectanglePolygon } from '@backfield/ui/axisAlignedRectangle'
import { LeafletMap } from '@backfield/ui/LeafletMap'
import { useAppMessage } from '@/components/AppMessageProvider'
import { ProcessedItemArticleBody } from '@/components/ProcessedItemArticleBody'
import { ProcessedItemVerificationLeafletMap } from '@/components/ProcessedItemVerificationLeafletMap'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { GeocodedPlaceEditForm } from '@/components/GeocodedPlaceEditForm'
import { GeocodedPlacesTable } from '@/components/GeocodedPlacesTable'
import { cn } from '@/lib/utils'
import type { Graph, ProcessedItem } from '@/lib/api'
import { getProcessedItem, patchProcessedItemOverlay } from '@/lib/api'
import { stylebookCanonicalDetailHref } from '@/lib/platformUrls'
import {
  applyAnchorPatchFragment,
  applyGeometryToPlaceRow,
  appendUserPlacePoint,
  buildVerificationLeafletCollections,
  extractGeometryFromPlace,
  isPolygonGeometry,
  stripSelectedVerificationPolygonsForEdit,
  getGeocodedPlaceDisplay,
  iterBaselinePlacesFromOutput,
  leafletBoundsFromGeometry,
  overlayAnchorGeometryChanged,
  shallowMergePlacePatch,
  validateGeometryObject,
} from '@/lib/processedItemPlaceGeometry'
import {
  applyPlaceEditFields,
  buildPlaceEditOverlayPatch,
  buildPlaceFieldsOnlyOverlayPatch,
  placeEditFieldsEqual,
  readPlaceEditFields,
  type PlaceEditFields,
} from '@/lib/processedItemPlaceEditFields'
import {
  getMergedRowPersistedLocationId,
  resolveProcessedItemArticleId,
  getMergedRowStylebookCanonicalId,
  getMergedRowStylebookLink,
  isReviewOnlyMergedRow,
  resolveStylebookSlugForLinkedRow,
} from '@/lib/processedItemReviewRow'
import {
  buildOccurrencesOverlayPayload,
  recomputeOccurrenceSpans,
  readMentionOccurrencesFromRow,
} from '@/lib/processedItemMentionOccurrences'
import {
  buildOccurrenceSpanHits,
  findAllMentionOccurrencesInArticle,
  resolveEvidenceSpansInArticle,
} from '@/lib/processedItemEvidenceSpan'
import {
  deleteSavedPlace,
  replaceSavedPlaceMentionOccurrences,
  updateSavedPlace,
  updateSavedPlaceGeometry,
  updateStylebookCanonicalGeometry,
} from '@/lib/stylebookLocationsApi'
import {
  getMergedRowAnchor,
  buildRemovePlaceOverlayPatch,
  normalizeOverlay,
  overlaysStructurallyEqual,
} from '@/lib/processedItemVerificationOverlay'
import { Loader2, MousePointer, Pencil, Square, Trash2 } from 'lucide-react'

/** Map height in the review column; table below uses remaining flex space and scrolls. */
const VERIFICATION_MAP_HEIGHT_PX = 300

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

  const [geometryEditing, setGeometryEditing] = useState(false)
  const [geometryDraft, setGeometryDraft] = useState<Record<string, unknown> | null | undefined>(
    undefined,
  )
  const [geometryBaseline, setGeometryBaseline] = useState<
    Record<string, unknown> | null | undefined
  >(undefined)
  const [placeFieldsDraft, setPlaceFieldsDraft] = useState<PlaceEditFields | undefined>(undefined)
  const [placeFieldsBaseline, setPlaceFieldsBaseline] = useState<PlaceEditFields | undefined>(
    undefined,
  )
  const [geometrySaving, setGeometrySaving] = useState(false)
  const [editPaneTab, setEditPaneTab] = useState<'map' | 'details'>('map')
  const [selectedAnchor, setSelectedAnchor] = useState<string | null>(null)
  const [selectedOccurrenceClientId, setSelectedOccurrenceClientId] = useState<string | null>(null)
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

  const selectedRow = useMemo(() => {
    if (!selectedAnchor) return undefined
    return previewMergedRows.find((r) => getMergedRowAnchor(r) === selectedAnchor)
  }, [previewMergedRows, selectedAnchor])

  const displayMergedRows = useMemo(() => {
    if (
      !geometryEditing ||
      !selectedAnchor ||
      geometryDraft === undefined ||
      placeFieldsDraft === undefined
    ) {
      return previewMergedRows
    }
    return previewMergedRows.map((row) => {
      if (getMergedRowAnchor(row) !== selectedAnchor) return row
      const loc = row.location as Record<string, unknown> | undefined
      if (!loc) return row
      const withFields = applyPlaceEditFields(loc, placeFieldsDraft)
      return {
        ...row,
        location: applyGeometryToPlaceRow(withFields, geometryDraft),
      }
    })
  }, [previewMergedRows, geometryEditing, selectedAnchor, geometryDraft, placeFieldsDraft])

  const geometryDirty = useMemo(() => {
    if (!geometryEditing || geometryDraft === undefined || geometryBaseline === undefined) {
      return false
    }
    return JSON.stringify(geometryDraft) !== JSON.stringify(geometryBaseline)
  }, [geometryEditing, geometryDraft, geometryBaseline])

  const placeFieldsDirty = useMemo(() => {
    if (
      !geometryEditing ||
      placeFieldsDraft === undefined ||
      placeFieldsBaseline === undefined
    ) {
      return false
    }
    return !placeEditFieldsEqual(placeFieldsDraft, placeFieldsBaseline)
  }, [geometryEditing, placeFieldsDraft, placeFieldsBaseline])

  const placeEditDirty = geometryDirty || placeFieldsDirty

  const storyHighlightAnchor = selectedAnchor

  /** All merged model and user-added places (including needs-review rows without geography). */
  const geocodedPlaceRows = useMemo(() => displayMergedRows, [displayMergedRows])

  const mapFocusBounds = useMemo(() => {
    if (!selectedAnchor) return null
    const row = displayMergedRows.find((r) => getMergedRowAnchor(r) === selectedAnchor)
    const loc = row?.location as Record<string, unknown> | undefined
    return leafletBoundsFromGeometry(extractGeometryFromPlace(loc ?? null))
  }, [displayMergedRows, selectedAnchor])

  const cancelGeometryEdit = useCallback(() => {
    setGeometryEditing(false)
    setGeometryDraft(undefined)
    setGeometryBaseline(undefined)
    setPlaceFieldsDraft(undefined)
    setPlaceFieldsBaseline(undefined)
    setSelectedOccurrenceClientId(null)
    setGeometryAddMode(null)
    setEditPaneTab('map')
  }, [])

  const selectPlaceAnchor = useCallback(
    (anchor: string) => {
      if (geometryEditing) {
        cancelGeometryEdit()
      }
      setSelectedAnchor(anchor)
      setSelectedOccurrenceClientId(null)
      setMapFocusBoundsKey((k) => k + 1)
      setGeometryAddMode(null)
    },
    [geometryEditing, cancelGeometryEdit],
  )

  const storyHighlightResult = useMemo(() => {
    const body = typeof article?.body === 'string' ? article.body : ''
    if (!storyHighlightAnchor) {
      return resolveEvidenceSpansInArticle(body, undefined)
    }
    const row = displayMergedRows.find((r) => getMergedRowAnchor(r) === storyHighlightAnchor)
    if (!row) {
      return resolveEvidenceSpansInArticle(body, undefined)
    }
    const occurrences =
      geometryEditing && placeFieldsDraft
        ? placeFieldsDraft.occurrences
        : readMentionOccurrencesFromRow(row as { location?: Record<string, unknown>; mention_occurrences?: unknown })
    const selected =
      selectedOccurrenceClientId != null
        ? occurrences.find((o) => o.clientId === selectedOccurrenceClientId && !o.suppressed)
        : null
    if (selected && body) {
      const withSpans = recomputeOccurrenceSpans(body, [selected])
      const hit = withSpans[0]
      if (hit && hit.startChar !== null && hit.endChar !== null) {
        return {
          kind: 'ranges' as const,
          ranges: [{ start: hit.startChar, end: hit.endChar }],
        }
      }
    }
    const active = occurrences.filter((o) => !o.suppressed && o.mentionText.trim())
    if (active.length > 0 && body) {
      const ranges = buildOccurrenceSpanHits(body, [
        { anchor: storyHighlightAnchor, occurrences: recomputeOccurrenceSpans(body, active) },
      ]).map(({ start, end }) => ({ start, end }))
      if (ranges.length > 0) {
        return { kind: 'ranges' as const, ranges }
      }
    }
    const loc = (row?.location ?? null) as Record<string, unknown> | null
    return resolveEvidenceSpansInArticle(body, loc ?? undefined)
  }, [
    article?.body,
    storyHighlightAnchor,
    displayMergedRows,
    geometryEditing,
    placeFieldsDraft,
    selectedOccurrenceClientId,
  ])

  const storyHighlightRanges =
    storyHighlightResult.kind === 'ranges' ? storyHighlightResult.ranges : []

  const allMentionTexts = useMemo(() => {
    const seen = new Set<string>()
    const texts: string[] = []
    for (const row of geocodedPlaceRows) {
      const occs = readMentionOccurrencesFromRow(
        row as { location?: Record<string, unknown>; mention_occurrences?: unknown },
      )
      for (const occ of occs) {
        if (occ.suppressed) continue
        const trimmed = occ.mentionText.trim()
        if (!trimmed) continue
        const key = trimmed.toLowerCase()
        if (seen.has(key)) continue
        seen.add(key)
        texts.push(trimmed)
      }
    }
    return texts
  }, [geocodedPlaceRows])

  const ambientHighlightRanges = useMemo(() => {
    const body = typeof article?.body === 'string' ? article.body : ''
    if (!body || allMentionTexts.length === 0) return []
    return findAllMentionOccurrencesInArticle(body, allMentionTexts)
  }, [article?.body, allMentionTexts])

  const mentionSpanHits = useMemo(() => {
    const body = typeof article?.body === 'string' ? article.body : ''
    if (!body) return []
    return buildOccurrenceSpanHits(
      body,
      geocodedPlaceRows
        .map((row) => {
          const anchor = getMergedRowAnchor(row)
          if (!anchor) return null
          const occs = readMentionOccurrencesFromRow(
            row as { location?: Record<string, unknown>; mention_occurrences?: unknown },
          )
          return {
            anchor,
            occurrences: recomputeOccurrenceSpans(body, occs),
          }
        })
        .filter((p): p is { anchor: string; occurrences: ReturnType<typeof recomputeOccurrenceSpans> } => p !== null),
    )
  }, [article?.body, geocodedPlaceRows])

  const placeLabelsByAnchor = useMemo(() => {
    const labels: Record<string, string> = {}
    for (const row of geocodedPlaceRows) {
      const anchor = getMergedRowAnchor(row)
      if (!anchor) continue
      const loc = row.location as Record<string, unknown> | undefined
      const display = getGeocodedPlaceDisplay(loc)
      labels[anchor] = display.name?.trim() || anchor
    }
    return labels
  }, [geocodedPlaceRows])

  useEffect(() => {
    if (!selectedAnchor) return
    const rowEl = document.getElementById(`geo-place-row-${selectedAnchor}`)
    rowEl?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selectedAnchor])

  const unsavedGeometryOverlay = useMemo(() => {
    if (!selectedAnchor) return false
    return overlayAnchorGeometryChanged(draftOverlay, baselineOverlay, selectedAnchor)
  }, [draftOverlay, baselineOverlay, selectedAnchor])

  const mapDraftGeometry = useMemo(() => {
    if (!selectedAnchor) return null
    if (geometryEditing && geometryDraft !== undefined) {
      return geometryDraft
    }
    const row = displayMergedRows.find((r) => getMergedRowAnchor(r) === selectedAnchor)
    const loc = row?.location as Record<string, unknown> | undefined
    return extractGeometryFromPlace(loc ?? null)
  }, [displayMergedRows, selectedAnchor, geometryEditing, geometryDraft])

  const hideSelectedPolygonForRectangleEdit = useMemo(() => {
    if (!geometryEditing || !selectedAnchor) return false
    if (geometryAddMode === 'rectangle') return true
    if (!mapDraftGeometry || !isPolygonGeometry(mapDraftGeometry)) return false
    return isAxisAlignedRectanglePolygon(mapDraftGeometry)
  }, [geometryEditing, selectedAnchor, geometryAddMode, mapDraftGeometry])

  const mapCollections = useMemo(() => {
    const base = buildVerificationLeafletCollections({
      mergedRows: displayMergedRows,
      baselineByAnchor,
      selectedAnchor,
      geometryEditing,
      unsavedGeometryOverlay,
    })
    if (!hideSelectedPolygonForRectangleEdit || !selectedAnchor) return base
    return stripSelectedVerificationPolygonsForEdit(base, selectedAnchor)
  }, [
    displayMergedRows,
    baselineByAnchor,
    selectedAnchor,
    geometryEditing,
    unsavedGeometryOverlay,
    hideSelectedPolygonForRectangleEdit,
  ])

  const editPointFeatureId = useMemo(() => {
    if (!selectedAnchor) return null
    const pts = mapCollections.points.features as Array<{ properties?: { id?: string } }>
    const draftId = `${selectedAnchor}__draft`
    if (pts.some((f) => f.properties?.id === draftId)) return draftId
    if (pts.some((f) => f.properties?.id === selectedAnchor)) return selectedAnchor
    return null
  }, [mapCollections.points.features, selectedAnchor])

  const handleMapGeometryChange = useCallback(
    (g: Record<string, unknown> | null) => {
      if (!selectedAnchor || !g || !geometryEditing) return
      const err = validateGeometryObject(g)
      if (err) {
        showError(err, { title: 'Map' })
        return
      }
      setGeometryDraft(g)
    },
    [selectedAnchor, geometryEditing, showError],
  )

  const startGeometryEdit = useCallback(() => {
    if (!selectedAnchor || !selectedRow) return
    const loc = selectedRow.location as Record<string, unknown> | undefined
    const g = extractGeometryFromPlace(loc ?? null)
    const fields = readPlaceEditFields(loc)
    setGeometryBaseline(g)
    setGeometryDraft(g)
    setPlaceFieldsBaseline(fields)
    setPlaceFieldsDraft(fields)
    setGeometryEditing(true)
    setGeometryAddMode(null)
    setEditPaneTab('map')
    setMapFocusBoundsKey((k) => k + 1)
  }, [selectedAnchor, selectedRow, article?.body])

  const saveGeometryForSelected = useCallback(async (): Promise<boolean> => {
    if (
      !selectedAnchor ||
      !selectedRow ||
      geometryDraft === undefined ||
      placeFieldsDraft === undefined ||
      geometrySaving
    ) {
      return false
    }
    if (geometryDirty && geometryDraft !== null) {
      const err = validateGeometryObject(geometryDraft)
      if (err) {
        showError(err, { title: 'Map' })
        return false
      }
    }
    const projectSlug =
      typeof catalogProjectSlug === 'string' && catalogProjectSlug.trim()
        ? catalogProjectSlug.trim()
        : ''
    const persistedId = getMergedRowPersistedLocationId(selectedRow)
    setGeometrySaving(true)
    try {
      const row = mergedRows.find((r) => getMergedRowAnchor(r) === selectedAnchor)
      const base = (row?.location as Record<string, unknown> | undefined) ?? {}
      const by = ((draftOverlay.locations as Record<string, unknown> | undefined)?.by_anchor ?? {}) as Record<
        string,
        unknown
      >
      const mergedBase = shallowMergePlacePatch(
        base,
        by[selectedAnchor] as Record<string, unknown> | undefined,
      )
      const body = typeof article?.body === 'string' ? article.body : ''
      const occurrencesWithSpans = body
        ? recomputeOccurrenceSpans(body, placeFieldsDraft.occurrences)
        : placeFieldsDraft.occurrences
      const fieldsForSave = { ...placeFieldsDraft, occurrences: occurrencesWithSpans }
      const fragment = geometryDirty
        ? buildPlaceEditOverlayPatch(mergedBase, fieldsForSave, geometryDraft)
        : buildPlaceFieldsOnlyOverlayPatch(mergedBase, fieldsForSave)

      if (persistedId !== null) {
        if (!projectSlug) {
          showError('This project does not have a slug configured for saving places.', {
            title: 'Could not save',
          })
          return false
        }
        const articleId = resolveProcessedItemArticleId(
          article,
          item.input,
          item.output ?? item.node_outputs,
        )
        if (geometryDirty) {
          await updateSavedPlaceGeometry(persistedId, projectSlug, geometryDraft)
        }
        await updateSavedPlace(persistedId, projectSlug, {
          name: fieldsForSave.label.trim() || null,
          location_type: fieldsForSave.type.trim() || null,
          formatted_address: fieldsForSave.formattedAddress.trim() || null,
        })
        if (articleId !== null) {
          await replaceSavedPlaceMentionOccurrences(
            persistedId,
            projectSlug,
            articleId,
            buildOccurrencesOverlayPayload(occurrencesWithSpans),
          )
        }
        const next = normalizeOverlay(draftOverlay)
        applyAnchorPatchFragment(next, selectedAnchor, fragment)
        const updated = await patchProcessedItemOverlay(
          runId,
          item.id,
          next,
          item.overlay_version ?? 0,
        )
        onItemUpdated(updated)
        const n = normalizeOverlay(updated.overlay)
        setBaselineOverlay(n)
        setDraftOverlay(n)
        cancelGeometryEdit()
        return true
      }

      const next = normalizeOverlay(draftOverlay)
      applyAnchorPatchFragment(next, selectedAnchor, fragment)
      const updated = await patchProcessedItemOverlay(
        runId,
        item.id,
        next,
        item.overlay_version ?? 0,
      )
      onItemUpdated(updated)
      const n = normalizeOverlay(updated.overlay)
      setBaselineOverlay(n)
      setDraftOverlay(n)
      cancelGeometryEdit()
      return true
    } catch {
      showError('We could not save your changes. Check your connection and try again.', {
        title: 'Could not save',
      })
      return false
    } finally {
      setGeometrySaving(false)
    }
  }, [
    selectedAnchor,
    selectedRow,
    geometryDraft,
    geometryDirty,
    placeFieldsDraft,
    geometrySaving,
    catalogProjectSlug,
    article,
    item.input,
    runId,
    item.id,
    item.overlay_version,
    mergedRows,
    draftOverlay,
    onItemUpdated,
    cancelGeometryEdit,
    showError,
  ])

  const handleAdoptForStylebook = useCallback(
    async (row: Record<string, unknown>) => {
      const canonicalId = getMergedRowStylebookCanonicalId(row)
      const stylebookSlug = resolveStylebookSlugForLinkedRow(row, catalogStylebookSlug)
      if (!stylebookSlug || !canonicalId) {
        showMessage(
          'This place is not linked to a Stylebook catalog, or the catalog could not be resolved.',
          { title: 'Stylebook' },
        )
        return
      }
      if (geometryEditing) {
        showMessage('Save or cancel your map edits before adopting geography for Stylebook.', {
          title: 'Unsaved map edits',
        })
        return
      }
      const link = getMergedRowStylebookLink(row)
      const ok = await showConfirm(
        link?.label
          ? `Update the Stylebook place “${link.label}” to use this story’s saved geography?`
          : 'Update the linked Stylebook place to use this story’s saved geography?',
        {
          title: 'Adopt for Stylebook',
          confirmLabel: 'Adopt for Stylebook',
          cancelLabel: 'Cancel',
          destructive: false,
        },
      )
      if (!ok) return
      setSaving(true)
      try {
        const fresh = await getProcessedItem(runId, item.id)
        const anchor = getMergedRowAnchor(row)
        const freshRow = (fresh.merged_locations ?? []).find((r) => getMergedRowAnchor(r) === anchor)
        const loc = freshRow?.location as Record<string, unknown> | undefined
        const geom = extractGeometryFromPlace(loc ?? null)
        if (!geom) {
          showError('This story’s place does not have saved geography to adopt.', {
            title: 'Adopt for Stylebook',
          })
          return
        }
        await updateStylebookCanonicalGeometry(canonicalId, stylebookSlug, geom)
        const updated = await getProcessedItem(runId, item.id)
        onItemUpdated(updated)
        if (anchor) {
          setSelectedAnchor(anchor)
        }
        showMessage('The Stylebook place now uses this story’s saved geography.', {
          title: 'Adopted for Stylebook',
        })
      } catch (e) {
        showError(e instanceof Error ? e.message : 'We could not update the Stylebook place.', {
          title: 'Adopt for Stylebook',
        })
      } finally {
        setSaving(false)
      }
    },
    [
      catalogStylebookSlug,
      geometryEditing,
      runId,
      item.id,
      onItemUpdated,
      showConfirm,
      showError,
      showMessage,
    ],
  )

  const handleDeletePlace = useCallback(
    async (row: Record<string, unknown>) => {
      const anchor = getMergedRowAnchor(row)
      if (!anchor) return
      const display = getGeocodedPlaceDisplay(row.location as Record<string, unknown> | undefined)
      const label = display.name?.trim() || 'this place'
      const ok = await showConfirm(
        `Remove “${label}” from this story? Mentions for this article will be removed. If no other stories use this saved place, it will be unlinked from your catalog and removed.`,
        {
          title: 'Remove place from story',
          confirmLabel: 'Remove from story',
          cancelLabel: 'Cancel',
          destructive: true,
        },
      )
      if (!ok) return

      if (geometryEditing) {
        cancelGeometryEdit()
      }

      const source = row.source === 'user' ? 'user' : 'model'
      const nextOverlay = buildRemovePlaceOverlayPatch(draftOverlay, anchor, source)
      const projectSlug =
        typeof catalogProjectSlug === 'string' && catalogProjectSlug.trim()
          ? catalogProjectSlug.trim()
          : ''
      const persistedId = getMergedRowPersistedLocationId(row)
      const stylebookSlug = resolveStylebookSlugForLinkedRow(row, catalogStylebookSlug)
      const articleId = resolveProcessedItemArticleId(
        article,
        item.input,
        item.output ?? item.node_outputs,
      )

      setSaving(true)
      try {
        if (persistedId && projectSlug) {
          await deleteSavedPlace(persistedId, projectSlug, articleId, stylebookSlug)
        }
        const updated = await patchProcessedItemOverlay(
          runId,
          item.id,
          nextOverlay,
          item.overlay_version ?? 0,
        )
        onItemUpdated(updated)
        const n = normalizeOverlay(updated.overlay)
        setBaselineOverlay(n)
        setDraftOverlay(n)
        if (selectedAnchor === anchor) {
          setSelectedAnchor(null)
        }
        showMessage(
          'The place was removed from this story. If it was linked in your catalog, check Stylebook candidates to link it again.',
          { title: 'Place removed' },
        )
      } catch (e) {
        showError(
          e instanceof Error ? e.message : 'We could not delete this place. Try again.',
          { title: 'Remove place' },
        )
      } finally {
        setSaving(false)
      }
    },
    [
      article,
      cancelGeometryEdit,
      catalogProjectSlug,
      catalogStylebookSlug,
      draftOverlay,
      geometryEditing,
      item.id,
      item.input,
      item.output,
      item.node_outputs,
      item.overlay_version,
      onItemUpdated,
      runId,
      selectedAnchor,
      showConfirm,
      showError,
      showMessage,
    ],
  )

  const handleOpenStylebookPlace = useCallback(
    (row: Record<string, unknown>) => {
      const canonicalId = getMergedRowStylebookCanonicalId(row)
      const stylebookSlug = resolveStylebookSlugForLinkedRow(row, catalogStylebookSlug)
      if (!stylebookSlug || !canonicalId) {
        return
      }
      const proj =
        typeof catalogProjectSlug === 'string' && catalogProjectSlug.trim()
          ? catalogProjectSlug.trim()
          : null
      const url = stylebookCanonicalDetailHref(stylebookSlug, canonicalId, proj)
      window.open(url, '_blank', 'noopener,noreferrer')
    },
    [catalogProjectSlug, catalogStylebookSlug],
  )

  const handleAddNewPointMode = useCallback(() => {
    setGeometryAddMode('point')
    setSelectedAnchor(null)
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
    <Card className="isolate overflow-hidden border-primary/30">
      <CardContent className="space-y-3 pt-6">
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

        <div
          className={cn(
            'grid min-h-0 gap-3 overflow-hidden lg:grid-cols-2 lg:items-stretch',
            geometryEditing
              ? 'h-[min(64rem,calc(100dvh-8rem))]'
              : 'h-[min(52rem,calc(100dvh-10rem))]',
          )}
        >
          <div className="flex h-full min-h-0 flex-col gap-2">
            <div className="shrink-0 space-y-1">
              <h2 className="text-lg font-semibold text-foreground">Review and edit places</h2>
              <p className="text-sm text-muted-foreground">
                Use the tools on this page to add, delete or edit places extracted from this text.
              </p>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto rounded-md border bg-muted/30 p-2.5 text-sm">
              {article?.resolution === 'none' && !article?.body?.trim() ? (
                <p className="text-sm text-muted-foreground">
                  No article text is available for this item yet.
                </p>
              ) : article?.body?.trim() ? (
                <>
                  <ProcessedItemArticleBody
                    body={article.body}
                    ambientHighlights={ambientHighlightRanges}
                    highlights={storyHighlightRanges}
                    scrollWhenKey={selectedAnchor}
                    mentionSpanHits={mentionSpanHits}
                    placeLabels={placeLabelsByAnchor}
                    onSelectPlace={selectPlaceAnchor}
                  />
                  {storyHighlightAnchor &&
                  storyHighlightRanges.length === 0 &&
                  storyHighlightResult.kind === 'none' &&
                  article.body.trim().length > 0 ? (
                    <p className="mt-2 border-t border-border/60 pt-2 text-xs text-muted-foreground">
                      No matching passage was found in this story for this place.
                    </p>
                  ) : null}
                </>
              ) : (
                <p className="text-sm text-muted-foreground">No story text is available for this item yet.</p>
              )}
            </div>
          </div>

          <div
            className={cn(
              'flex h-full min-h-0 min-w-0 flex-col gap-2 overflow-hidden rounded-lg border bg-card p-2.5',
              geometryEditing && 'border-primary/40 bg-background',
            )}
          >
            <div className="flex w-full shrink-0 flex-wrap items-center gap-2">
              {selectedAnchor && !geometryEditing ? (
                <Button
                  type="button"
                  size="sm"
                  className="bg-black text-white hover:bg-black/90"
                  onClick={() => startGeometryEdit()}
                >
                  <Pencil className="mr-2 h-4 w-4" />
                  Edit
                </Button>
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
              {!geometryEditing ? (
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
              ) : null}
              {geometryEditing && mapDraftGeometry ? (
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  disabled={geometrySaving}
                  onClick={() => {
                    void (async () => {
                      const ok = await showConfirm('Clear this geography from the map?', {
                        title: 'Clear geometry',
                        confirmLabel: 'Clear',
                        destructive: true,
                      })
                      if (!ok) return
                      setGeometryDraft(null)
                      setGeometryAddMode(null)
                    })()
                  }}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  Clear geometry
                </Button>
              ) : null}
              {geometryEditing && selectedAnchor ? (
                <div className="ml-auto flex shrink-0 items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={geometrySaving}
                    onClick={() => cancelGeometryEdit()}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    disabled={!placeEditDirty || geometrySaving}
                    onClick={() => void saveGeometryForSelected()}
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
                      {geometryAddMode === 'point' && selectedAnchor === null ? (
                        <LeafletMap
                          points={mapCollections.points as any}
                          polygons={mapCollections.polygons as any}
                          geocoder
                          showPopups={false}
                          fitToData={false}
                          height={VERIFICATION_MAP_HEIGHT_PX}
                          fillHeight
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
                          mapEditing={geometryEditing}
                          geometryAddMode={geometryAddMode}
                          onGeometryAddModeChange={setGeometryAddMode}
                          editPointFeatureId={editPointFeatureId}
                          draftGeometry={mapDraftGeometry}
                          onDraftGeometryChange={handleMapGeometryChange}
                          mapHeightPx={VERIFICATION_MAP_HEIGHT_PX}
                          mapFillHeight
                          focusBounds={mapFocusBounds}
                          focusBoundsKey={mapFocusBoundsKey}
                          onFeatureSelect={(anchor) => {
                            selectPlaceAnchor(anchor)
                          }}
                        />
                      )}
                    </div>
                    {geometryAddMode === 'rectangle' ? (
                      <p className="shrink-0 text-xs text-muted-foreground">
                        Hold Shift and drag on the map to draw an axis-aligned rectangle.
                      </p>
                    ) : selectedRow && isReviewOnlyMergedRow(selectedRow) ? (
                      <p className="shrink-0 text-xs text-muted-foreground">
                        These changes are saved with this review only until the place is persisted for this
                        story.
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
                        onSelectOccurrence={setSelectedOccurrenceClientId}
                        onChange={setPlaceFieldsDraft}
                      />
                    ) : null}
                  </TabsContent>
                </div>
              </Tabs>
            ) : (
              <div className="relative z-0 w-full shrink-0 overflow-hidden rounded-md bg-background">
                {geometryAddMode === 'point' && selectedAnchor === null ? (
                  <LeafletMap
                    points={mapCollections.points as any}
                    polygons={mapCollections.polygons as any}
                    geocoder
                    showPopups={false}
                    fitToData={false}
                    height={VERIFICATION_MAP_HEIGHT_PX}
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
                    mapEditing={false}
                    geometryAddMode={geometryAddMode}
                    onGeometryAddModeChange={setGeometryAddMode}
                    editPointFeatureId={editPointFeatureId}
                    draftGeometry={mapDraftGeometry}
                    onDraftGeometryChange={handleMapGeometryChange}
                    mapHeightPx={VERIFICATION_MAP_HEIGHT_PX}
                    mapFillHeight={false}
                    focusBounds={mapFocusBounds}
                    focusBoundsKey={mapFocusBoundsKey}
                    onFeatureSelect={(anchor) => {
                      selectPlaceAnchor(anchor)
                    }}
                  />
                )}
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
                  getRowAnchor={getMergedRowAnchor}
                  onSelectAnchor={selectPlaceAnchor}
                  onOpenStylebookPlace={handleOpenStylebookPlace}
                  onAdoptForStylebook={(row) => void handleAdoptForStylebook(row)}
                  adoptDisabled={saving || geometrySaving}
                  onDeletePlace={(row) => void handleDeletePlace(row)}
                  deleteDisabled={saving || geometrySaving}
                />
              </div>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
