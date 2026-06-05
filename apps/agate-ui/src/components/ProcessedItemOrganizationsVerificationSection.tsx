import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AddOrganizationWorkflowPanel,
  type AddOrganizationWorkflowCreatedPayload,
} from '@/components/AddOrganizationWorkflowPanel'
import { useAppMessage } from '@/components/AppMessageProvider'
import {
  ProcessedItemArticleBody,
  type ArticleTextSelection,
} from '@/components/ProcessedItemArticleBody'
import { ProcessedItemOrganizationsEditor } from '@/components/ProcessedItemOrganizationsEditor'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import type { Graph, ProcessedItem } from '@/lib/api'
import { patchProcessedItemOverlay } from '@/lib/api'
import {
  stylebookOrganizationsCandidatesHref,
  stylebookOrganizationCanonicalDetailHref,
} from '@/lib/platformUrls'
import {
  buildOccurrenceSpanHits,
  findAllMentionOccurrencesInArticle,
  resolveEvidenceSpansInArticle,
} from '@/lib/review/content/evidenceSpan'
import { readMentionOccurrencesFromRow, recomputeOccurrenceSpans, resolveOccurrenceSpansInArticle, buildOccurrencesOverlayPayload, type MentionOccurrenceDraft } from '@/lib/review/entities/location/mentionOccurrences'
import { resolveProcessedItemArticleId } from '@/lib/review/entities/location/reviewRow'
import {
  buildOrganizationEditOverlayPatch,
  organizationEditFieldsEqual,
  readOrganizationEditFields,
  type OrganizationEditFields,
} from '@/lib/review/entities/organization/organizationEditFields'
import {
  getMergedRowAnchor,
  getMergedRowPersistedOrganizationId,
  getMergedRowStylebookOrganizationCanonicalId,
  organizationDisplayName,
  readOrganizationFromRow,
  resolveStylebookSlugForLinkedRow,
} from '@/lib/review/entities/organization/reviewRow'
import {
  appendUserAddedOrganizationToOverlay,
  applyOrganizationAnchorPatch,
  buildRemoveOrganizationOverlayPatch,
  buildUserAddedOrganizationOverlayRow,
  normalizeOverlay,
  overlaysStructurallyEqual,
} from '@/lib/review/overlay/verificationOverlay'
import { deleteSavedOrganization, replaceSavedOrganizationMentionOccurrences, updateSavedOrganization } from '@/lib/stylebookOrganizationsApi'
import { cn } from '@/lib/utils'
import { Plus } from 'lucide-react'

export interface ProcessedItemOrganizationsVerificationSectionProps {
  runId: string
  item: ProcessedItem
  graph: Graph | null
  onItemUpdated: (item: ProcessedItem) => void
  onVerificationDirtyChange?: (dirty: boolean) => void
  catalogStylebookSlug?: string | null
  catalogProjectSlug?: string | null
  /** When a rerun is in flight; organization review cannot be edited. */
  reviewLocked?: boolean
}

export function ProcessedItemOrganizationsVerificationSection({
  runId,
  item,
  onItemUpdated,
  onVerificationDirtyChange,
  catalogStylebookSlug = null,
  catalogProjectSlug = null,
  reviewLocked = false,
}: ProcessedItemOrganizationsVerificationSectionProps) {
  const { showError, showConfirm, showMessage } = useAppMessage()
  const [baselineOverlay, setBaselineOverlay] = useState<Record<string, unknown>>(() =>
    normalizeOverlay(item.overlay),
  )
  const [draftOverlay, setDraftOverlay] = useState<Record<string, unknown>>(() =>
    normalizeOverlay(item.overlay),
  )
  const [saving, setSaving] = useState(false)
  const [organizationEditing, setOrganizationEditing] = useState(false)
  const [selectedAnchor, setSelectedAnchor] = useState<string | null>(null)
  const [fieldsDraft, setFieldsDraft] = useState<OrganizationEditFields | undefined>(undefined)
  const [fieldsBaseline, setFieldsBaseline] = useState<OrganizationEditFields | undefined>(undefined)
  const [addOrganizationMode, setAddOrganizationMode] = useState(false)
  const [addOrganizationSelection, setAddOrganizationSelection] = useState<ArticleTextSelection | null>(null)
  const [awaitingAddOrganizationReselection, setAwaitingAddOrganizationReselection] = useState(false)
  const [articleTextSelection, setArticleTextSelection] = useState<ArticleTextSelection | null>(null)
  const [selectedOccurrenceClientId, setSelectedOccurrenceClientId] = useState<string | null>(null)
  const lastItemSyncKeyRef = useRef('')

  const dirty = useMemo(
    () => !overlaysStructurallyEqual(baselineOverlay, draftOverlay),
    [baselineOverlay, draftOverlay],
  )

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
  }, [item.overlay, item.overlay_version, syncKey, dirty])

  const mergedRows = useMemo(
    () => (Array.isArray(item.merged_organizations) ? item.merged_organizations : []),
    [item.merged_organizations],
  )

  const displayMergedRows = useMemo(() => {
    const patches =
      draftOverlay.organizations &&
      typeof draftOverlay.organizations === 'object' &&
      !Array.isArray(draftOverlay.organizations)
        ? ((draftOverlay.organizations as Record<string, unknown>).by_anchor as Record<string, unknown>)
        : {}
    const removed =
      draftOverlay.organizations &&
      typeof draftOverlay.organizations === 'object' &&
      !Array.isArray(draftOverlay.organizations)
        ? ((draftOverlay.organizations as Record<string, unknown>).removed_anchors as string[])
        : []
    const removedSet = new Set(Array.isArray(removed) ? removed : [])
    return mergedRows
      .filter((row) => {
        const anchor = getMergedRowAnchor(row)
        return anchor && !removedSet.has(anchor)
      })
      .map((row) => {
        const anchor = getMergedRowAnchor(row)
        const patch = patches?.[anchor]
        if (!patch || typeof patch !== 'object') return row
        const organization = readOrganizationFromRow(row)
        const mergedOrganization = { ...organization, ...(patch as Record<string, unknown>) }
        return { ...row, organization: mergedOrganization }
      })
  }, [mergedRows, draftOverlay])

  const selectedRow = useMemo(
    () => displayMergedRows.find((r) => getMergedRowAnchor(r) === selectedAnchor) ?? null,
    [displayMergedRows, selectedAnchor],
  )

  const articleId = useMemo(
    () => resolveProcessedItemArticleId(item.article_context, item.input, item.output ?? undefined),
    [item],
  )

  const persistAddOrganizationToStylebook = (articleId ?? 0) > 0
  const article = item.article_context

  const fieldsDirty =
    organizationEditing &&
    fieldsDraft !== undefined &&
    fieldsBaseline !== undefined &&
    !organizationEditFieldsEqual(fieldsDraft, fieldsBaseline)

  const organizationEditDirty = fieldsDirty || dirty

  useEffect(() => {
    onVerificationDirtyChange?.(organizationEditDirty)
  }, [organizationEditDirty, onVerificationDirtyChange])

  const cancelOrganizationEdit = useCallback(() => {
    setOrganizationEditing(false)
    setFieldsDraft(undefined)
    setFieldsBaseline(undefined)
    setSelectedOccurrenceClientId(null)
    setArticleTextSelection(null)
  }, [])

  const startOrganizationEdit = useCallback(() => {
    if (!selectedRow) return
    const fields = readOrganizationEditFields(readOrganizationFromRow(selectedRow), selectedRow)
    setFieldsBaseline(fields)
    setFieldsDraft(fields)
    setSelectedOccurrenceClientId(null)
    setArticleTextSelection(null)
    setOrganizationEditing(true)
  }, [selectedRow])

  const storyHighlightResult = useMemo(() => {
    const body = typeof article?.body === 'string' ? article.body : ''
    if (!selectedAnchor) {
      return { mentionRanges: [] as Array<{ start: number; end: number }>, quoteRanges: [] as Array<{ start: number; end: number }> }
    }
    const row = displayMergedRows.find((r) => getMergedRowAnchor(r) === selectedAnchor)
    if (!row) {
      return { mentionRanges: [], quoteRanges: [] }
    }
    const occurrences =
      organizationEditing && fieldsDraft
        ? fieldsDraft.occurrences
        : readMentionOccurrencesFromRow({
            location: readOrganizationFromRow(row),
            mention_occurrences: row.mention_occurrences,
          })
    const selectedOccurrence =
      !organizationEditing && selectedOccurrenceClientId != null
        ? occurrences.find((o) => o.clientId === selectedOccurrenceClientId && !o.suppressed)
        : null
    if (selectedOccurrence && body) {
      const span = resolveOccurrenceSpansInArticle(body, selectedOccurrence)
      if (span) {
        if (selectedOccurrence.isQuote) {
          return { mentionRanges: [], quoteRanges: [span] }
        }
        return { mentionRanges: [span], quoteRanges: [] }
      }
    }
    const active = recomputeOccurrenceSpans(
      body,
      occurrences.filter((o) => !o.suppressed && o.mentionText.trim()),
    )
    if (active.length > 0 && body) {
      const mentionRanges: Array<{ start: number; end: number }> = []
      const quoteRanges: Array<{ start: number; end: number }> = []
      for (const occ of active) {
        const span = resolveOccurrenceSpansInArticle(body, occ)
        if (!span) continue
        if (occ.isQuote) {
          quoteRanges.push(span)
        } else {
          mentionRanges.push(span)
        }
      }
      if (mentionRanges.length > 0 || quoteRanges.length > 0) {
        return { mentionRanges, quoteRanges }
      }
    }
    if (organizationEditing && fieldsDraft) {
      return { mentionRanges: [], quoteRanges: [] }
    }
    const fallback = resolveEvidenceSpansInArticle(body, readOrganizationFromRow(row))
    if (fallback.kind === 'ranges') {
      return { mentionRanges: fallback.ranges, quoteRanges: [] }
    }
    return { mentionRanges: [], quoteRanges: [] }
  }, [
    article?.body,
    selectedAnchor,
    displayMergedRows,
    organizationEditing,
    fieldsDraft,
    selectedOccurrenceClientId,
  ])

  const storyMentionHighlightRanges = storyHighlightResult.mentionRanges
  const storyQuoteHighlightRanges = storyHighlightResult.quoteRanges

  const editableOccurrenceClientIds = useMemo(() => {
    if (!organizationEditing || !fieldsDraft || !article?.body?.trim()) return undefined
    const withSpans = recomputeOccurrenceSpans(
      article.body,
      fieldsDraft.occurrences.filter((o) => !o.suppressed),
    )
    const map: Record<string, string> = {}
    for (const occ of withSpans) {
      if (occ.startChar === null || occ.endChar === null) continue
      map[`${occ.startChar}:${occ.endChar}`] = occ.clientId
    }
    return map
  }, [organizationEditing, fieldsDraft, article?.body])

  const addOccurrenceFromSelection = useCallback(
    (selection: ArticleTextSelection, kind: 'mention' | 'quote') => {
      if (!fieldsDraft) return
      const maxOrder = fieldsDraft.occurrences.reduce(
        (max, occ) => Math.max(max, occ.occurrenceOrder),
        -1,
      )
      const clientId =
        typeof crypto !== 'undefined' && crypto.randomUUID
          ? crypto.randomUUID()
          : `occ-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
      const trimmed = selection.text.trim()
      const nextOccurrence: MentionOccurrenceDraft = {
        clientId,
        mentionText: trimmed,
        quoteText: trimmed,
        isQuote: kind === 'quote',
        startChar: selection.start,
        endChar: selection.end,
        occurrenceOrder: maxOrder + 1,
        suppressed: false,
      }
      setFieldsDraft({
        ...fieldsDraft,
        occurrences: [...fieldsDraft.occurrences, nextOccurrence],
      })
      setSelectedOccurrenceClientId(clientId)
      setArticleTextSelection(null)
      window.getSelection()?.removeAllRanges()
    },
    [fieldsDraft],
  )

  const removeOccurrenceClientId = useCallback(
    (clientId: string) => {
      if (!fieldsDraft) return
      setSelectedOccurrenceClientId(null)
      setFieldsDraft({
        ...fieldsDraft,
        occurrences: fieldsDraft.occurrences.map((occ) =>
          occ.clientId === clientId ? { ...occ, suppressed: true } : occ,
        ),
      })
    },
    [fieldsDraft],
  )

  const activeStoryMentionHighlightRanges = useMemo(
    () =>
      addOrganizationSelection
        ? [
            ...storyMentionHighlightRanges,
            { start: addOrganizationSelection.start, end: addOrganizationSelection.end },
          ]
        : storyMentionHighlightRanges,
    [addOrganizationSelection, storyMentionHighlightRanges],
  )

  const ambientHighlightRanges = useMemo(() => {
    if (organizationEditing) return []
    const body = typeof article?.body === 'string' ? article.body : ''
    if (!body.trim()) return []
    const needles: string[] = []
    for (const row of displayMergedRows) {
      const occs = readMentionOccurrencesFromRow({
        location: readOrganizationFromRow(row),
        mention_occurrences: row.mention_occurrences,
      })
      for (const occ of occs) {
        if (!occ.suppressed && occ.mentionText.trim()) {
          needles.push(occ.mentionText.trim())
        }
      }
    }
    return findAllMentionOccurrencesInArticle(body, needles)
  }, [article?.body, displayMergedRows, organizationEditing])

  const mentionSpanHits = useMemo(() => {
    const body = typeof article?.body === 'string' ? article.body : ''
    if (!body) return []
    const rows =
      organizationEditing && selectedAnchor
        ? displayMergedRows.filter((row) => getMergedRowAnchor(row) === selectedAnchor)
        : displayMergedRows
    return buildOccurrenceSpanHits(
      body,
      rows
        .map((row) => {
          const anchor = getMergedRowAnchor(row)
          if (!anchor) return null
          const occs =
            organizationEditing && fieldsDraft && anchor === selectedAnchor
              ? fieldsDraft.occurrences
              : readMentionOccurrencesFromRow({
                  location: readOrganizationFromRow(row),
                  mention_occurrences: row.mention_occurrences,
                })
          return {
            anchor,
            occurrences: recomputeOccurrenceSpans(body, occs),
          }
        })
        .filter(
          (entry): entry is { anchor: string; occurrences: ReturnType<typeof recomputeOccurrenceSpans> } =>
            entry !== null,
        ),
    )
  }, [article?.body, displayMergedRows, organizationEditing, fieldsDraft, selectedAnchor])

  const organizationLabelsByAnchor = useMemo(() => {
    const labels: Record<string, string> = {}
    const rows =
      organizationEditing && selectedAnchor
        ? displayMergedRows.filter((row) => getMergedRowAnchor(row) === selectedAnchor)
        : displayMergedRows
    for (const row of rows) {
      const anchor = getMergedRowAnchor(row)
      if (!anchor) continue
      labels[anchor] = organizationDisplayName(row)
    }
    return labels
  }, [displayMergedRows, organizationEditing, selectedAnchor])

  const selectOrganizationAnchor = useCallback(
    (anchor: string) => {
      if (organizationEditing) {
        cancelOrganizationEdit()
      }
      setAddOrganizationMode(false)
      setAddOrganizationSelection(null)
      setSelectedAnchor(anchor)
    },
    [organizationEditing, cancelOrganizationEdit],
  )

  const handleUnselect = useCallback(() => {
    if (organizationEditing) {
      cancelOrganizationEdit()
    }
    setSelectedAnchor(null)
  }, [organizationEditing, cancelOrganizationEdit])

  const handleBeginAddOrganization = useCallback((selection: ArticleTextSelection) => {
    setAddOrganizationMode(false)
    setSelectedAnchor(null)
    setAddOrganizationSelection(selection)
    setAwaitingAddOrganizationReselection(false)
    setArticleTextSelection(null)
  }, [])

  const cancelAddOrganizationWorkflow = useCallback(() => {
    setAddOrganizationMode(false)
    setAddOrganizationSelection(null)
    setAwaitingAddOrganizationReselection(false)
    setArticleTextSelection(null)
    const sel = window.getSelection()
    sel?.removeAllRanges()
  }, [])

  const addOrganizationWorkflowActive = addOrganizationMode || addOrganizationSelection !== null

  const articleInteractionMode = useMemo(() => {
    if (reviewLocked) {
      return 'locked' as const
    }
    if (addOrganizationSelection && !awaitingAddOrganizationReselection) {
      return 'locked' as const
    }
    if (addOrganizationMode || awaitingAddOrganizationReselection) {
      return 'select-passage' as const
    }
    return 'normal' as const
  }, [reviewLocked, addOrganizationSelection, awaitingAddOrganizationReselection, addOrganizationMode])

  useEffect(() => {
    if (!reviewLocked) return
    cancelOrganizationEdit()
    cancelAddOrganizationWorkflow()
  }, [reviewLocked, cancelOrganizationEdit, cancelAddOrganizationWorkflow])

  useEffect(() => {
    if (!addOrganizationWorkflowActive || addOrganizationSelection) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') cancelAddOrganizationWorkflow()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [addOrganizationWorkflowActive, addOrganizationSelection, cancelAddOrganizationWorkflow])

  useEffect(() => {
    if (!selectedAnchor) return
    const rowEl = document.getElementById(`organizations-row-${selectedAnchor}`)
    rowEl?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selectedAnchor])

  const handleAddOrganizationCreated = useCallback(
    async (payload: AddOrganizationWorkflowCreatedPayload) => {
      const userAddedRow = buildUserAddedOrganizationOverlayRow({
        anchor: payload.anchor,
        name: payload.name,
        organizationType: payload.organizationType,
        nature: payload.nature,
        mentionText: payload.mentionText,
        quoteText: payload.selection.text,
        startChar: payload.selection.start,
        endChar: payload.selection.end,
        roleInStory: payload.roleInStory,
      })
      const nextOverlay = appendUserAddedOrganizationToOverlay(draftOverlay, userAddedRow)
      try {
        const updated = await patchProcessedItemOverlay(
          runId,
          item.id,
          nextOverlay,
          item.overlay_version ?? 0,
        )
        onItemUpdated(updated)
        setBaselineOverlay(normalizeOverlay(updated.overlay))
        setDraftOverlay(normalizeOverlay(updated.overlay))
        setAddOrganizationSelection(null)
        setAwaitingAddOrganizationReselection(false)
        setAddOrganizationMode(false)
        setSelectedAnchor(payload.anchor)
        showMessage('Organization added to this review.', { title: 'Organizations review' })
      } catch (err) {
        showError(err instanceof Error ? err.message : 'Could not save organization.', {
          title: 'Organizations review',
        })
      }
    },
    [draftOverlay, runId, item.id, item.overlay_version, onItemUpdated, showError, showMessage],
  )

  const handleSaveOrganizationEdit = useCallback(async (): Promise<boolean> => {
    if (saving || !selectedAnchor || !selectedRow || fieldsDraft === undefined) {
      return false
    }
    const projectSlug =
      typeof catalogProjectSlug === 'string' && catalogProjectSlug.trim()
        ? catalogProjectSlug.trim()
        : ''
    const persistedId = getMergedRowPersistedOrganizationId(selectedRow)
    setSaving(true)
    try {
      const body = typeof article?.body === 'string' ? article.body : ''
      const occurrencesWithSpans = body
        ? recomputeOccurrenceSpans(body, fieldsDraft.occurrences)
        : fieldsDraft.occurrences
      const fieldsForSave = { ...fieldsDraft, occurrences: occurrencesWithSpans }
      const fragment = buildOrganizationEditOverlayPatch(fieldsForSave)
      if (persistedId !== null) {
        if (!projectSlug) {
          showError('This project does not have a slug configured for saving organizations.', {
            title: 'Could not save',
          })
          return false
        }
        await updateSavedOrganization(
          persistedId,
          projectSlug,
          {
            name: fieldsDraft.name,
            organization_type: fieldsDraft.organizationType,
            role_in_story: fieldsDraft.roleInStory,
            nature: fieldsDraft.nature,
            nature_secondary_tags: fieldsDraft.natureSecondaryTags,
          },
          articleId,
        )
        if (articleId !== null) {
          await replaceSavedOrganizationMentionOccurrences(
            persistedId,
            projectSlug,
            articleId,
            buildOccurrencesOverlayPayload(occurrencesWithSpans) as any,
          )
        }
      }
      const nextOverlay = applyOrganizationAnchorPatch(draftOverlay, selectedAnchor, fragment)
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
      setFieldsBaseline(fieldsForSave)
      cancelOrganizationEdit()
      return true
    } catch {
      showError('We could not save your changes. Check your connection and try again.', {
        title: 'Could not save',
      })
      return false
    } finally {
      setSaving(false)
    }
  }, [
    saving,
    selectedAnchor,
    selectedRow,
    fieldsDraft,
    catalogProjectSlug,
    articleId,
    article?.body,
    draftOverlay,
    runId,
    item.id,
    item.overlay_version,
    onItemUpdated,
    showError,
    cancelOrganizationEdit,
  ])

  const saveOverlayReview = useCallback(async () => {
    if (saving || !dirty) return
    setSaving(true)
    try {
      const updated = await patchProcessedItemOverlay(
        runId,
        item.id,
        draftOverlay,
        item.overlay_version ?? 0,
      )
      onItemUpdated(updated)
      const normalized = normalizeOverlay(updated.overlay)
      setBaselineOverlay(normalized)
      setDraftOverlay(normalized)
      showMessage('Review saved', { title: 'Organizations review' })
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Save failed', { title: 'Organizations review' })
    } finally {
      setSaving(false)
    }
  }, [
    saving,
    dirty,
    draftOverlay,
    runId,
    item.id,
    item.overlay_version,
    onItemUpdated,
    showError,
    showMessage,
  ])

  const handleOpenStylebook = useCallback(
    (row: Record<string, unknown>) => {
      if (dirty || fieldsDirty || organizationEditing) {
        showError('Save your review changes before opening Stylebook.', {
          title: 'Organizations review',
        })
        return
      }
      const slug = catalogStylebookSlug
      if (!slug) {
        showError('No Stylebook is linked to this workspace.', { title: 'Stylebook' })
        return
      }
      const canonicalId = getMergedRowStylebookOrganizationCanonicalId(row)
      const href = canonicalId
        ? stylebookOrganizationCanonicalDetailHref(slug, canonicalId, catalogProjectSlug)
        : stylebookOrganizationsCandidatesHref(slug, catalogProjectSlug)
      window.open(href, '_blank', 'noopener,noreferrer')
    },
    [dirty, fieldsDirty, organizationEditing, catalogStylebookSlug, catalogProjectSlug, showError],
  )

  const handleDeleteOrganization = useCallback(
    async (row: Record<string, unknown>) => {
      const anchor = getMergedRowAnchor(row)
      if (!anchor) return
      const label = organizationDisplayName(row)
      const ok = await showConfirm(
        `Remove “${label}” from this story? Mentions for this article will be removed. If no other stories use this saved organization, they will be unlinked from your catalog and removed.`,
        {
          title: 'Remove organization from story',
          confirmLabel: 'Remove from story',
          cancelLabel: 'Cancel',
          destructive: true,
        },
      )
      if (!ok) return

      if (organizationEditing) {
        cancelOrganizationEdit()
      }

      const source = row.source === 'user' ? 'user' : 'model'
      const nextOverlay = buildRemoveOrganizationOverlayPatch(draftOverlay, anchor, source)
      const projectSlug =
        typeof catalogProjectSlug === 'string' && catalogProjectSlug.trim()
          ? catalogProjectSlug.trim()
          : ''
      const persistedId = getMergedRowPersistedOrganizationId(row)
      const stylebookSlug = resolveStylebookSlugForLinkedRow(row, catalogStylebookSlug)

      setSaving(true)
      try {
        if (persistedId && projectSlug) {
          await deleteSavedOrganization(persistedId, projectSlug, articleId, stylebookSlug)
        }
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
        if (selectedAnchor === anchor) {
          setSelectedAnchor(null)
        }
        showMessage(
          'The organization was removed from this story. If they were linked in your catalog, check Stylebook candidates to link them again.',
          { title: 'Organization removed' },
        )
      } catch (e) {
        showError(
          e instanceof Error ? e.message : 'We could not delete this organization. Try again.',
          { title: 'Remove organization' },
        )
      } finally {
        setSaving(false)
      }
    },
    [
      showConfirm,
      organizationEditing,
      cancelOrganizationEdit,
      draftOverlay,
      catalogProjectSlug,
      catalogStylebookSlug,
      articleId,
      runId,
      item.id,
      item.overlay_version,
      onItemUpdated,
      selectedAnchor,
      showError,
      showMessage,
    ],
  )

  const hasArticleBody = Boolean(article?.body?.trim())

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Review and edit organizations</h2>
          <p className="text-sm text-muted-foreground">
            Select an organization to highlight its mentions, then choose Edit to change details.
          </p>
        </div>
        {hasArticleBody ? (
          <Button
            type="button"
            variant={addOrganizationMode ? 'outline' : 'default'}
            size="sm"
            disabled={reviewLocked || addOrganizationSelection !== null}
            onClick={() => {
              if (reviewLocked || addOrganizationSelection) return
              if (articleTextSelection) {
                handleBeginAddOrganization(articleTextSelection)
                return
              }
              if (addOrganizationMode) {
                cancelAddOrganizationWorkflow()
                return
              }
              setAddOrganizationMode(true)
            }}
          >
            {addOrganizationMode ? null : <Plus className="mr-2 h-4 w-4" />}
            {addOrganizationMode ? 'Cancel' : 'Add organization'}
          </Button>
        ) : null}
      </div>

      {(dirty || fieldsDirty) && !organizationEditing && (
        <Alert>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
            <span>You have unsaved organizations review changes.</span>
            <Button
              type="button"
              size="sm"
              disabled={saving || reviewLocked}
              onClick={() => void saveOverlayReview()}
            >
              Save review
            </Button>
          </AlertDescription>
        </Alert>
      )}

      <div
        className={cn(
          'grid min-h-0 gap-4 lg:grid-cols-2 lg:items-stretch',
          addOrganizationSelection || organizationEditing
            ? 'h-[min(52rem,calc(100dvh-10rem))]'
            : 'h-[min(44rem,calc(100dvh-12rem))]',
        )}
      >
        <div
          className={cn(
            'min-h-0 overflow-y-auto rounded-md border p-2.5 text-sm',
            addOrganizationMode || organizationEditing
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
              {organizationEditing ? (
                <p
                  className="mb-2 rounded-md border border-primary/30 bg-primary/10 px-2.5 py-2 text-sm text-foreground"
                  role="status"
                >
                  Highlight to add a mention or quote. Hover and click X to remove.
                </p>
              ) : null}
              {(addOrganizationMode || awaitingAddOrganizationReselection) ? (
                <div
                  className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-md border border-primary/30 bg-primary/10 px-2.5 py-2"
                  role="status"
                >
                  <p className="text-sm text-foreground">
                    {awaitingAddOrganizationReselection
                      ? 'Highlight a new passage in the story for this organization.'
                      : 'Highlight the passage in the story that supports this organization.'}
                  </p>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 shrink-0 px-2"
                    onClick={() => {
                      if (awaitingAddOrganizationReselection) {
                        setAwaitingAddOrganizationReselection(false)
                        setArticleTextSelection(null)
                        window.getSelection()?.removeAllRanges()
                        return
                      }
                      cancelAddOrganizationWorkflow()
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              ) : null}
              {(selectedAnchor && !addOrganizationMode && (organizationEditing || storyMentionHighlightRanges.length > 0 || storyQuoteHighlightRanges.length > 0)) ? (
                <div
                  className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground"
                  role="note"
                >
                  <span className="inline-flex items-center gap-1.5">
                    <span
                      aria-hidden
                      className="inline-block h-3 w-6 rounded-sm border border-transparent bg-amber-200/90 dark:bg-amber-500/40"
                    />
                    Mention
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span
                      aria-hidden
                      className="inline-block h-3 w-6 rounded-sm border border-transparent bg-sky-200/90 dark:bg-sky-500/40"
                    />
                    Quote
                  </span>
                </div>
              ) : null}
              <ProcessedItemArticleBody
                body={article.body}
                ambientHighlights={ambientHighlightRanges}
                highlights={activeStoryMentionHighlightRanges}
                quoteHighlights={storyQuoteHighlightRanges}
                scrollWhenKey={
                  selectedAnchor
                    ? `${selectedAnchor}:${selectedOccurrenceClientId ?? ''}`
                    : null
                }
                mentionSpanHits={mentionSpanHits}
                placeLabels={organizationLabelsByAnchor}
                interactionMode={articleInteractionMode}
                onSelectPlace={
                  reviewLocked || addOrganizationWorkflowActive || organizationEditing
                    ? undefined
                    : selectOrganizationAnchor
                }
                mentionChoicePrompt="Which organization?"
                onTextSelectionChange={(selection) => {
                  if (addOrganizationSelection && !awaitingAddOrganizationReselection) return
                  setArticleTextSelection(selection)
                  if ((addOrganizationMode || awaitingAddOrganizationReselection) && selection) {
                    handleBeginAddOrganization(selection)
                  }
                }}
                activeTextSelection={organizationEditing ? articleTextSelection : null}
                onAddOccurrenceFromSelection={
                  organizationEditing ? addOccurrenceFromSelection : undefined
                }
                editableOccurrenceClientIds={editableOccurrenceClientIds}
                selectedOccurrenceClientId={selectedOccurrenceClientId}
                onSelectOccurrenceClientId={
                  organizationEditing ? setSelectedOccurrenceClientId : undefined
                }
                onRemoveOccurrenceClientId={
                  organizationEditing ? removeOccurrenceClientId : undefined
                }
                className={
                  addOrganizationMode || awaitingAddOrganizationReselection || organizationEditing
                    ? 'cursor-text'
                    : undefined
                }
              />
              {selectedAnchor &&
              !organizationEditing &&
              storyMentionHighlightRanges.length === 0 &&
              storyQuoteHighlightRanges.length === 0 &&
              article.body.trim().length > 0 ? (
                <p className="mt-2 border-t border-border/60 pt-2 text-xs text-muted-foreground">
                  No matching passage was found in this story for this organization.
                </p>
              ) : null}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No story text is available for this item yet.</p>
          )}
        </div>

        {addOrganizationSelection ? (
          <AddOrganizationWorkflowPanel
            projectSlug={catalogProjectSlug?.trim() ?? ''}
            runId={runId}
            articleId={articleId ?? 0}
            persistToStylebook={persistAddOrganizationToStylebook}
            selection={addOrganizationSelection}
            awaitingNewSelection={awaitingAddOrganizationReselection}
            onChangeSelection={() => {
              setAwaitingAddOrganizationReselection(true)
              setArticleTextSelection(null)
              const sel = window.getSelection()
              sel?.removeAllRanges()
            }}
            onCancel={cancelAddOrganizationWorkflow}
            onCreated={(createdPayload) => {
              void handleAddOrganizationCreated(createdPayload)
            }}
            onError={(message, title) => showError(message, { title })}
          />
        ) : (
          <ProcessedItemOrganizationsEditor
            organizationEditing={organizationEditing}
            selectedAnchor={selectedAnchor}
            selectedRow={selectedRow}
            rows={displayMergedRows}
            fieldsDraft={fieldsDraft}
            fieldsDirty={fieldsDirty}
            saving={saving}
            reviewLocked={reviewLocked}
            onSelectAnchor={selectOrganizationAnchor}
            onOpenStylebook={handleOpenStylebook}
            onStartEdit={startOrganizationEdit}
            onCancelEdit={cancelOrganizationEdit}
            onSaveEdit={() => void handleSaveOrganizationEdit()}
            onDeleteOrganization={(row) => void handleDeleteOrganization(row)}
            onUnselect={handleUnselect}
            onFieldsChange={setFieldsDraft}
          />
        )}
      </div>
    </div>
  )
}
