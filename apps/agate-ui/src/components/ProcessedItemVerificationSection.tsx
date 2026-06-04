import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { isAxisAlignedRectanglePolygon } from '@backfield/ui/axisAlignedRectangle'
import { useAppMessage } from '@/components/AppMessageProvider'
import {
  ProcessedItemArticleBody,
  type ArticleTextSelection,
} from '@/components/ProcessedItemArticleBody'
import { ProcessedItemPlaceGeographyEditor } from '@/components/ProcessedItemPlaceGeographyEditor'
import {
  AddPlaceWorkflowPanel,
  type AddPlaceWorkflowCreatedPayload,
} from '@/components/AddPlaceWorkflowPanel'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { Graph, ProcessedItem } from '@/lib/api'
import { getProcessedItem, patchProcessedItemOverlay } from '@/lib/api'
import { stylebookCanonicalDetailHref } from '@/lib/platformUrls'
import {
  applyAnchorPatchFragment,
  applyGeometryToPlaceRow,
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
} from '@/lib/review/entities/location/placeGeometry'
import {
  applyPlaceEditFields,
  buildPlaceEditOverlayPatch,
  buildPlaceFieldsOnlyOverlayPatch,
  placeEditFieldsEqual,
  readPlaceEditFields,
  type PlaceEditFields,
} from '@/lib/review/entities/location/placeEditFields'
import {
  getMergedRowPersistedLocationId,
  resolveProcessedItemArticleId,
  getMergedRowStylebookCanonicalId,
  getMergedRowStylebookLink,
  isReviewOnlyMergedRow,
  resolveStylebookSlugForLinkedRow,
} from '@/lib/review/entities/location/reviewRow'
import { Plus } from 'lucide-react'
import {
  buildOccurrencesOverlayPayload,
  recomputeOccurrenceSpans,
  readMentionOccurrencesFromRow,
} from '@/lib/review/entities/location/mentionOccurrences'
import {
  buildOccurrenceSpanHits,
  findAllMentionOccurrencesInArticle,
  resolveEvidenceSpansInArticle,
} from '@/lib/review/content/evidenceSpan'
import {
  deleteSavedPlace,
  replaceSavedPlaceMentionOccurrences,
  updateSavedPlace,
  updateSavedPlaceGeometry,
  updateStylebookCanonicalGeometry,
} from '@/lib/stylebookLocationsApi'
import {
  appendUserAddedPlaceToOverlay,
  buildRemovePlaceOverlayPatch,
  buildUserAddedOverlayRow,
  getMergedRowAnchor,
  normalizeOverlay,
  overlaysStructurallyEqual,
} from '@/lib/review/overlay/verificationOverlay'

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
  const [articleTextSelection, setArticleTextSelection] = useState<ArticleTextSelection | null>(null)
  const [addPlaceMode, setAddPlaceMode] = useState(false)
  const [addPlaceSelection, setAddPlaceSelection] = useState<ArticleTextSelection | null>(null)
  const [awaitingAddPlaceReselection, setAwaitingAddPlaceReselection] = useState(false)
  const [pendingGeometryStartAnchor, setPendingGeometryStartAnchor] = useState<string | null>(null)
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
  const articleIdForStylebook = resolveProcessedItemArticleId(
    article,
    item.input,
    item.output ?? item.node_outputs ?? undefined,
  )
  const persistAddPlaceToStylebook = (articleIdForStylebook ?? 0) > 0

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
      setAddPlaceMode(false)
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
  const activeStoryHighlightRanges = useMemo(
    () =>
      addPlaceSelection
        ? [
            ...storyHighlightRanges,
            { start: addPlaceSelection.start, end: addPlaceSelection.end },
          ]
        : storyHighlightRanges,
    [addPlaceSelection, storyHighlightRanges],
  )

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

  useEffect(() => {
    if (!pendingGeometryStartAnchor || geometryEditing) return
    if (selectedAnchor !== pendingGeometryStartAnchor) return
    if (!selectedRow) return
    setPendingGeometryStartAnchor(null)
    startGeometryEdit()
  }, [
    pendingGeometryStartAnchor,
    geometryEditing,
    selectedAnchor,
    selectedRow,
    startGeometryEdit,
  ])

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
          item.output ?? item.node_outputs ?? undefined,
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
            buildOccurrencesOverlayPayload(occurrencesWithSpans) as any,
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
        item.output ?? item.node_outputs ?? undefined,
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

  const handleBeginAddPlace = useCallback(
    (selection: ArticleTextSelection) => {
      if (geometryEditing) {
        cancelGeometryEdit()
      }
      setAddPlaceMode(false)
      setSelectedAnchor(null)
      setAddPlaceSelection(selection)
      setAwaitingAddPlaceReselection(false)
      setArticleTextSelection(null)
    },
    [geometryEditing, cancelGeometryEdit],
  )

  const cancelAddPlaceWorkflow = useCallback(() => {
    setAddPlaceMode(false)
    setAddPlaceSelection(null)
    setAwaitingAddPlaceReselection(false)
    setArticleTextSelection(null)
    const sel = window.getSelection()
    sel?.removeAllRanges()
  }, [])

  const addPlaceWorkflowActive = addPlaceMode || addPlaceSelection !== null

  const articleInteractionMode = useMemo(() => {
    if (addPlaceSelection && !awaitingAddPlaceReselection) {
      return 'locked' as const
    }
    if (addPlaceMode || awaitingAddPlaceReselection) {
      return 'select-passage' as const
    }
    return 'normal' as const
  }, [addPlaceSelection, awaitingAddPlaceReselection, addPlaceMode])

  useEffect(() => {
    if (!addPlaceWorkflowActive || addPlaceSelection) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') cancelAddPlaceWorkflow()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [addPlaceWorkflowActive, addPlaceSelection, cancelAddPlaceWorkflow])

  const handleAddPlaceCreated = useCallback(
    async (payload: AddPlaceWorkflowCreatedPayload) => {
      const { anchor, label, locationType, mentionText, roleInStory, selection, created } = payload
      const userAddedRow = buildUserAddedOverlayRow({
        anchor,
        label,
        locationType,
        mentionText,
        roleInStory,
        quoteText: selection.text,
        startChar: selection.start,
        endChar: selection.end,
        formattedAddress: created?.location.formatted_address,
        geometry: created?.location.geometry_json,
      })
      const nextOverlay = appendUserAddedPlaceToOverlay(draftOverlay, userAddedRow)
      try {
        const updated = await patchProcessedItemOverlay(
          runId,
          item.id,
          nextOverlay,
          item.overlay_version ?? 0,
        )
        onItemUpdated(updated)
        const normalized = normalizeOverlay(updated.overlay)
        setBaselineOverlay(normalized)
        setDraftOverlay(normalized)
      } catch {
        showError(
          'The place was saved, but we could not update the reviewed output. Try saving your review again.',
          { title: 'Review output' },
        )
        const updated = await getProcessedItem(runId, item.id)
        onItemUpdated(updated)
      }
      setAddPlaceMode(false)
      setAddPlaceSelection(null)
      setAwaitingAddPlaceReselection(false)
      setArticleTextSelection(null)
      setSelectedAnchor(anchor)
      setPendingGeometryStartAnchor(anchor)
      setGeometryAddMode(null)
      setMapFocusBoundsKey((k) => k + 1)
    },
    [draftOverlay, item.id, item.overlay_version, onItemUpdated, runId, showError],
  )

  const handleFindOnMap = useCallback(
    (row: Record<string, unknown>) => {
      const anchor = getMergedRowAnchor(row)
      if (!anchor) return
      if (geometryEditing) {
        cancelGeometryEdit()
      }
      setSelectedAnchor(anchor)
      setPendingGeometryStartAnchor(anchor)
      setGeometryAddMode(null)
      setMapFocusBoundsKey((k) => k + 1)
    },
    [geometryEditing, cancelGeometryEdit],
  )

  const handleShowAllOnMap = useCallback(() => {
    if (geometryEditing) {
      cancelGeometryEdit()
    }
    setSelectedAnchor(null)
    setPendingGeometryStartAnchor(null)
    setArticleTextSelection(null)
    setMapFocusBoundsKey((k) => k + 1)
  }, [geometryEditing, cancelGeometryEdit])

  return (
    <Card className="isolate overflow-hidden border-primary/30">
      <CardContent className="space-y-3 pt-6">
        {staleEntries.length > 0 ? (
          <Alert
            variant="default"
            className="border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-50"
          >
            <AlertDescription>
              Place data for this article has been corrected or enhanced by an editor.
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="grid shrink-0 gap-x-3 gap-y-1 lg:grid-cols-2 lg:items-start">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold text-foreground">Review and edit places</h2>
            <p className="text-sm text-muted-foreground">
              Use the tools on this page to add, delete or edit places extracted from this text.
            </p>
          </div>
          {article?.body?.trim() ? (
            <div className="flex justify-end lg:col-start-2">
              <Button
                type="button"
                size="sm"
                className={cn(
                  'shrink-0',
                  addPlaceMode ? undefined : 'bg-black text-white hover:bg-black/90',
                )}
                variant={addPlaceMode ? 'outline' : 'default'}
                disabled={addPlaceSelection !== null}
                onClick={() => {
                  if (addPlaceSelection) return
                  if (articleTextSelection) {
                    handleBeginAddPlace(articleTextSelection)
                    return
                  }
                  if (addPlaceMode) {
                    cancelAddPlaceWorkflow()
                    return
                  }
                  setAddPlaceMode(true)
                }}
              >
                {addPlaceMode ? null : <Plus className="mr-2 h-4 w-4" />}
                {addPlaceMode ? 'Cancel' : 'Add place'}
              </Button>
            </div>
          ) : null}
        </div>

        <div
          className={cn(
            'grid min-h-0 gap-3 overflow-hidden lg:grid-cols-2 lg:items-stretch',
            geometryEditing || addPlaceSelection
              ? 'h-[min(64rem,calc(100dvh-8rem))]'
              : 'h-[min(52rem,calc(100dvh-10rem))]',
          )}
        >
          <div
            className={cn(
              'min-h-0 overflow-y-auto rounded-md border p-2.5 text-sm transition-[border-color,box-shadow,background-color]',
              addPlaceMode
                ? 'border-primary/50 bg-primary/5 ring-2 ring-primary/20'
                : 'border-border bg-muted/30',
            )}
          >
              {article?.resolution === 'none' && !article?.body?.trim() ? (
                <p className="text-sm text-muted-foreground">
                  No article text is available for this item yet.
                </p>
              ) : article?.body?.trim() ? (
                <>
                  {addPlaceMode || awaitingAddPlaceReselection ? (
                    <div
                      className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-md border border-primary/30 bg-primary/10 px-2.5 py-2"
                      role="status"
                    >
                      <p className="text-sm text-foreground">
                        {awaitingAddPlaceReselection
                          ? 'Highlight a new passage in the story for this place.'
                          : 'Highlight the passage in the story that supports this place.'}
                      </p>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-7 shrink-0 px-2"
                        onClick={() => {
                          if (awaitingAddPlaceReselection) {
                            setAwaitingAddPlaceReselection(false)
                            setArticleTextSelection(null)
                            window.getSelection()?.removeAllRanges()
                            return
                          }
                          cancelAddPlaceWorkflow()
                        }}
                      >
                        Cancel
                      </Button>
                    </div>
                  ) : null}
                  <ProcessedItemArticleBody
                    body={article.body}
                    ambientHighlights={ambientHighlightRanges}
                    highlights={activeStoryHighlightRanges}
                    scrollWhenKey={selectedAnchor}
                    mentionSpanHits={mentionSpanHits}
                    placeLabels={placeLabelsByAnchor}
                    interactionMode={articleInteractionMode}
                    onSelectPlace={
                      addPlaceWorkflowActive ? undefined : selectPlaceAnchor
                    }
                    onTextSelectionChange={(selection) => {
                      if (addPlaceSelection && !awaitingAddPlaceReselection) return
                      setArticleTextSelection(selection)
                      if ((addPlaceMode || awaitingAddPlaceReselection) && selection) {
                        handleBeginAddPlace(selection)
                      }
                    }}
                    activeTextSelection={null}
                    onAddPlaceFromSelection={undefined}
                    className={
                      addPlaceMode || awaitingAddPlaceReselection ? 'cursor-text' : undefined
                    }
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

          {addPlaceSelection ? (
            <AddPlaceWorkflowPanel
              projectSlug={catalogProjectSlug?.trim() ?? ''}
              runId={runId}
              articleId={articleIdForStylebook ?? 0}
              persistToStylebook={persistAddPlaceToStylebook}
              selection={addPlaceSelection}
              awaitingNewSelection={awaitingAddPlaceReselection}
              onChangeSelection={() => {
                setAwaitingAddPlaceReselection(true)
                setArticleTextSelection(null)
                const sel = window.getSelection()
                sel?.removeAllRanges()
              }}
              onCancel={cancelAddPlaceWorkflow}
              onCreated={(createdPayload) => {
                void handleAddPlaceCreated(createdPayload)
              }}
              onError={(message, title) => showError(message, { title })}
            />
          ) : (
            <ProcessedItemPlaceGeographyEditor
              geometryEditing={geometryEditing}
              selectedAnchor={selectedAnchor}
              mapDraftGeometry={mapDraftGeometry}
              geometryAddMode={geometryAddMode}
              geometrySaving={geometrySaving}
              placeEditDirty={placeEditDirty}
              placeFieldsDirty={placeFieldsDirty}
              editPaneTab={editPaneTab}
              placeFieldsDraft={placeFieldsDraft}
              selectedOccurrenceClientId={selectedOccurrenceClientId}
              selectedRow={selectedRow}
              mapCollections={mapCollections}
              editPointFeatureId={editPointFeatureId}
              mapFocusBounds={mapFocusBounds}
              mapFocusBoundsKey={mapFocusBoundsKey}
              geocodedPlaceRows={geocodedPlaceRows}
              staleAnchorSet={staleAnchorSet}
              saving={saving}
              startGeometryEdit={startGeometryEdit}
              setGeometryAddMode={setGeometryAddMode}
              clearGeometry={() => {
                void (async () => {
                  const ok = await showConfirm('Clear this geography from the map?', {
                    title: 'Clear geography',
                    confirmLabel: 'Clear',
                    destructive: true,
                  })
                  if (!ok) return
                  setGeometryDraft(null)
                  setGeometryAddMode(null)
                })()
              }}
              cancelGeometryEdit={cancelGeometryEdit}
              saveGeometryForSelected={() => void saveGeometryForSelected()}
              setEditPaneTab={setEditPaneTab}
              onPlaceFieldsDraftChange={setPlaceFieldsDraft}
              onSelectedOccurrenceChange={setSelectedOccurrenceClientId}
              onMapGeometryChange={handleMapGeometryChange}
              onSelectAnchor={selectPlaceAnchor}
              getRowAnchor={getMergedRowAnchor}
              onOpenStylebookPlace={handleOpenStylebookPlace}
              onAdoptForStylebook={(row) => void handleAdoptForStylebook(row)}
              onDeletePlace={(row) => void handleDeletePlace(row)}
              onShowAll={handleShowAllOnMap}
              onFindOnMap={handleFindOnMap}
              cancelLabel={!mapDraftGeometry ? 'Finish later' : 'Cancel'}
            />
          )}
        </div>
      </CardContent>
    </Card>
  )
}
