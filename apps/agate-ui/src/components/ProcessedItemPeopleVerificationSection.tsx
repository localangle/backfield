import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AddPersonWorkflowPanel,
  type AddPersonWorkflowCreatedPayload,
} from '@/components/AddPersonWorkflowPanel'
import { useAppMessage } from '@/components/AppMessageProvider'
import {
  ProcessedItemArticleBody,
  type ArticleTextSelection,
} from '@/components/ProcessedItemArticleBody'
import { ProcessedItemPeopleEditor } from '@/components/ProcessedItemPeopleEditor'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import type { Graph, ProcessedItem } from '@/lib/api'
import { patchProcessedItemOverlay } from '@/lib/api'
import {
  stylebookPeopleCandidatesHref,
  stylebookPersonCanonicalDetailHref,
} from '@/lib/platformUrls'
import {
  buildOccurrenceSpanHits,
  findAllMentionOccurrencesInArticle,
  resolveEvidenceSpansInArticle,
} from '@/lib/review/content/evidenceSpan'
import { readMentionOccurrencesFromRow, recomputeOccurrenceSpans, resolveOccurrenceSpansInArticle, buildOccurrencesOverlayPayload, type MentionOccurrenceDraft } from '@/lib/review/entities/location/mentionOccurrences'
import { resolveProcessedItemArticleId } from '@/lib/review/entities/location/reviewRow'
import {
  buildPersonEditOverlayPatch,
  personEditFieldsEqual,
  readPersonEditFields,
  type PersonEditFields,
} from '@/lib/review/entities/person/personEditFields'
import {
  getMergedRowAnchor,
  getMergedRowPersistedPersonId,
  getMergedRowStylebookPersonCanonicalId,
  personDisplayName,
  readPersonFromRow,
  resolveStylebookSlugForLinkedRow,
} from '@/lib/review/entities/person/reviewRow'
import {
  appendUserAddedPersonToOverlay,
  applyPersonAnchorPatch,
  buildRemovePersonOverlayPatch,
  buildUserAddedPersonOverlayRow,
  normalizeOverlay,
  overlaysStructurallyEqual,
} from '@/lib/review/overlay/verificationOverlay'
import { deleteSavedPerson, replaceSavedPersonMentionOccurrences, updateSavedPerson } from '@/lib/stylebookPeopleApi'
import { cn } from '@/lib/utils'
import { Plus } from 'lucide-react'

export interface ProcessedItemPeopleVerificationSectionProps {
  runId: string
  item: ProcessedItem
  graph: Graph | null
  onItemUpdated: (item: ProcessedItem) => void
  onVerificationDirtyChange?: (dirty: boolean) => void
  catalogStylebookSlug?: string | null
  catalogProjectSlug?: string | null
}

export function ProcessedItemPeopleVerificationSection({
  runId,
  item,
  onItemUpdated,
  onVerificationDirtyChange,
  catalogStylebookSlug = null,
  catalogProjectSlug = null,
}: ProcessedItemPeopleVerificationSectionProps) {
  const { showError, showConfirm, showMessage } = useAppMessage()
  const [baselineOverlay, setBaselineOverlay] = useState<Record<string, unknown>>(() =>
    normalizeOverlay(item.overlay),
  )
  const [draftOverlay, setDraftOverlay] = useState<Record<string, unknown>>(() =>
    normalizeOverlay(item.overlay),
  )
  const [saving, setSaving] = useState(false)
  const [personEditing, setPersonEditing] = useState(false)
  const [selectedAnchor, setSelectedAnchor] = useState<string | null>(null)
  const [fieldsDraft, setFieldsDraft] = useState<PersonEditFields | undefined>(undefined)
  const [fieldsBaseline, setFieldsBaseline] = useState<PersonEditFields | undefined>(undefined)
  const [addPersonMode, setAddPersonMode] = useState(false)
  const [addPersonSelection, setAddPersonSelection] = useState<ArticleTextSelection | null>(null)
  const [awaitingAddPersonReselection, setAwaitingAddPersonReselection] = useState(false)
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
    () => (Array.isArray(item.merged_people) ? item.merged_people : []),
    [item.merged_people],
  )

  const displayMergedRows = useMemo(() => {
    const patches =
      draftOverlay.people &&
      typeof draftOverlay.people === 'object' &&
      !Array.isArray(draftOverlay.people)
        ? ((draftOverlay.people as Record<string, unknown>).by_anchor as Record<string, unknown>)
        : {}
    const removed =
      draftOverlay.people &&
      typeof draftOverlay.people === 'object' &&
      !Array.isArray(draftOverlay.people)
        ? ((draftOverlay.people as Record<string, unknown>).removed_anchors as string[])
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
        const person = readPersonFromRow(row)
        const mergedPerson = { ...person, ...(patch as Record<string, unknown>) }
        return { ...row, person: mergedPerson }
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

  const persistAddPersonToStylebook = (articleId ?? 0) > 0
  const article = item.article_context

  const fieldsDirty =
    personEditing &&
    fieldsDraft !== undefined &&
    fieldsBaseline !== undefined &&
    !personEditFieldsEqual(fieldsDraft, fieldsBaseline)

  const personEditDirty = fieldsDirty || dirty

  useEffect(() => {
    onVerificationDirtyChange?.(personEditDirty)
  }, [personEditDirty, onVerificationDirtyChange])

  const cancelPersonEdit = useCallback(() => {
    setPersonEditing(false)
    setFieldsDraft(undefined)
    setFieldsBaseline(undefined)
    setSelectedOccurrenceClientId(null)
    setArticleTextSelection(null)
  }, [])

  const startPersonEdit = useCallback(() => {
    if (!selectedRow) return
    const fields = readPersonEditFields(readPersonFromRow(selectedRow), selectedRow)
    setFieldsBaseline(fields)
    setFieldsDraft(fields)
    setSelectedOccurrenceClientId(null)
    setArticleTextSelection(null)
    setPersonEditing(true)
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
      personEditing && fieldsDraft
        ? fieldsDraft.occurrences
        : readMentionOccurrencesFromRow({
            location: readPersonFromRow(row),
            mention_occurrences: row.mention_occurrences,
          })
    const selectedOccurrence =
      !personEditing && selectedOccurrenceClientId != null
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
    if (personEditing && fieldsDraft) {
      return { mentionRanges: [], quoteRanges: [] }
    }
    const fallback = resolveEvidenceSpansInArticle(body, readPersonFromRow(row))
    if (fallback.kind === 'ranges') {
      return { mentionRanges: fallback.ranges, quoteRanges: [] }
    }
    return { mentionRanges: [], quoteRanges: [] }
  }, [
    article?.body,
    selectedAnchor,
    displayMergedRows,
    personEditing,
    fieldsDraft,
    selectedOccurrenceClientId,
  ])

  const storyMentionHighlightRanges = storyHighlightResult.mentionRanges
  const storyQuoteHighlightRanges = storyHighlightResult.quoteRanges

  const editableOccurrenceClientIds = useMemo(() => {
    if (!personEditing || !fieldsDraft || !article?.body?.trim()) return undefined
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
  }, [personEditing, fieldsDraft, article?.body])

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
      addPersonSelection
        ? [
            ...storyMentionHighlightRanges,
            { start: addPersonSelection.start, end: addPersonSelection.end },
          ]
        : storyMentionHighlightRanges,
    [addPersonSelection, storyMentionHighlightRanges],
  )

  const ambientHighlightRanges = useMemo(() => {
    if (personEditing) return []
    const body = typeof article?.body === 'string' ? article.body : ''
    if (!body.trim()) return []
    const needles: string[] = []
    for (const row of displayMergedRows) {
      const occs = readMentionOccurrencesFromRow({
        location: readPersonFromRow(row),
        mention_occurrences: row.mention_occurrences,
      })
      for (const occ of occs) {
        if (!occ.suppressed && occ.mentionText.trim()) {
          needles.push(occ.mentionText.trim())
        }
      }
    }
    return findAllMentionOccurrencesInArticle(body, needles)
  }, [article?.body, displayMergedRows, personEditing])

  const mentionSpanHits = useMemo(() => {
    const body = typeof article?.body === 'string' ? article.body : ''
    if (!body) return []
    const rows =
      personEditing && selectedAnchor
        ? displayMergedRows.filter((row) => getMergedRowAnchor(row) === selectedAnchor)
        : displayMergedRows
    return buildOccurrenceSpanHits(
      body,
      rows
        .map((row) => {
          const anchor = getMergedRowAnchor(row)
          if (!anchor) return null
          const occs =
            personEditing && fieldsDraft && anchor === selectedAnchor
              ? fieldsDraft.occurrences
              : readMentionOccurrencesFromRow({
                  location: readPersonFromRow(row),
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
  }, [article?.body, displayMergedRows, personEditing, fieldsDraft, selectedAnchor])

  const personLabelsByAnchor = useMemo(() => {
    const labels: Record<string, string> = {}
    const rows =
      personEditing && selectedAnchor
        ? displayMergedRows.filter((row) => getMergedRowAnchor(row) === selectedAnchor)
        : displayMergedRows
    for (const row of rows) {
      const anchor = getMergedRowAnchor(row)
      if (!anchor) continue
      labels[anchor] = personDisplayName(row)
    }
    return labels
  }, [displayMergedRows, personEditing, selectedAnchor])

  const selectPersonAnchor = useCallback(
    (anchor: string) => {
      if (personEditing) {
        cancelPersonEdit()
      }
      setAddPersonMode(false)
      setAddPersonSelection(null)
      setSelectedAnchor(anchor)
    },
    [personEditing, cancelPersonEdit],
  )

  const handleUnselect = useCallback(() => {
    if (personEditing) {
      cancelPersonEdit()
    }
    setSelectedAnchor(null)
  }, [personEditing, cancelPersonEdit])

  const handleBeginAddPerson = useCallback((selection: ArticleTextSelection) => {
    setAddPersonMode(false)
    setSelectedAnchor(null)
    setAddPersonSelection(selection)
    setAwaitingAddPersonReselection(false)
    setArticleTextSelection(null)
  }, [])

  const cancelAddPersonWorkflow = useCallback(() => {
    setAddPersonMode(false)
    setAddPersonSelection(null)
    setAwaitingAddPersonReselection(false)
    setArticleTextSelection(null)
    const sel = window.getSelection()
    sel?.removeAllRanges()
  }, [])

  const addPersonWorkflowActive = addPersonMode || addPersonSelection !== null

  const articleInteractionMode = useMemo(() => {
    if (addPersonSelection && !awaitingAddPersonReselection) {
      return 'locked' as const
    }
    if (addPersonMode || awaitingAddPersonReselection) {
      return 'select-passage' as const
    }
    return 'normal' as const
  }, [addPersonSelection, awaitingAddPersonReselection, addPersonMode])

  useEffect(() => {
    if (!addPersonWorkflowActive || addPersonSelection) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') cancelAddPersonWorkflow()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [addPersonWorkflowActive, addPersonSelection, cancelAddPersonWorkflow])

  useEffect(() => {
    if (!selectedAnchor) return
    const rowEl = document.getElementById(`people-row-${selectedAnchor}`)
    rowEl?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selectedAnchor])

  const handleAddPersonCreated = useCallback(
    async (payload: AddPersonWorkflowCreatedPayload) => {
      const userAddedRow = buildUserAddedPersonOverlayRow({
        anchor: payload.anchor,
        name: payload.name,
        personType: payload.personType,
        title: payload.title,
        affiliation: payload.affiliation,
        nature: payload.nature,
        publicFigure: payload.publicFigure,
        mentionText: payload.mentionText,
        quoteText: payload.selection.text,
        startChar: payload.selection.start,
        endChar: payload.selection.end,
        roleInStory: payload.roleInStory,
      })
      const nextOverlay = appendUserAddedPersonToOverlay(draftOverlay, userAddedRow)
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
        setAddPersonSelection(null)
        setAwaitingAddPersonReselection(false)
        setAddPersonMode(false)
        setSelectedAnchor(payload.anchor)
        showMessage('Person added to this review.', { title: 'People review' })
      } catch (err) {
        showError(err instanceof Error ? err.message : 'Could not save person.', {
          title: 'People review',
        })
      }
    },
    [draftOverlay, runId, item.id, item.overlay_version, onItemUpdated, showError, showMessage],
  )

  const handleSavePersonEdit = useCallback(async (): Promise<boolean> => {
    if (saving || !selectedAnchor || !selectedRow || fieldsDraft === undefined) {
      return false
    }
    const projectSlug =
      typeof catalogProjectSlug === 'string' && catalogProjectSlug.trim()
        ? catalogProjectSlug.trim()
        : ''
    const persistedId = getMergedRowPersistedPersonId(selectedRow)
    setSaving(true)
    try {
      const body = typeof article?.body === 'string' ? article.body : ''
      const occurrencesWithSpans = body
        ? recomputeOccurrenceSpans(body, fieldsDraft.occurrences)
        : fieldsDraft.occurrences
      const fieldsForSave = { ...fieldsDraft, occurrences: occurrencesWithSpans }
      const fragment = buildPersonEditOverlayPatch(fieldsForSave)
      if (persistedId !== null) {
        if (!projectSlug) {
          showError('This project does not have a slug configured for saving people.', {
            title: 'Could not save',
          })
          return false
        }
        await updateSavedPerson(
          persistedId,
          projectSlug,
          {
            name: fieldsDraft.name,
            title: fieldsDraft.title,
            affiliation: fieldsDraft.affiliation,
            person_type: fieldsDraft.personType,
            role_in_story: fieldsDraft.roleInStory,
            nature: fieldsDraft.nature,
            public_figure: fieldsDraft.publicFigure,
            sort_key: fieldsDraft.sortKey.trim() || null,
          },
          articleId,
        )
        if (articleId !== null) {
          await replaceSavedPersonMentionOccurrences(
            persistedId,
            projectSlug,
            articleId,
            buildOccurrencesOverlayPayload(occurrencesWithSpans) as any,
          )
        }
      }
      const nextOverlay = applyPersonAnchorPatch(draftOverlay, selectedAnchor, fragment)
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
      cancelPersonEdit()
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
    cancelPersonEdit,
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
      showMessage('Review saved', { title: 'People review' })
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Save failed', { title: 'People review' })
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
      if (dirty || fieldsDirty || personEditing) {
        showError('Save your review changes before opening Stylebook.', { title: 'People review' })
        return
      }
      const slug = catalogStylebookSlug
      if (!slug) {
        showError('No Stylebook is linked to this workspace.', { title: 'Stylebook' })
        return
      }
      const canonicalId = getMergedRowStylebookPersonCanonicalId(row)
      const href = canonicalId
        ? stylebookPersonCanonicalDetailHref(slug, canonicalId, catalogProjectSlug)
        : stylebookPeopleCandidatesHref(slug, catalogProjectSlug)
      window.open(href, '_blank', 'noopener,noreferrer')
    },
    [dirty, fieldsDirty, personEditing, catalogStylebookSlug, catalogProjectSlug, showError],
  )

  const handleDeletePerson = useCallback(
    async (row: Record<string, unknown>) => {
      const anchor = getMergedRowAnchor(row)
      if (!anchor) return
      const label = personDisplayName(row)
      const ok = await showConfirm(
        `Remove “${label}” from this story? Mentions for this article will be removed. If no other stories use this saved person, they will be unlinked from your catalog and removed.`,
        {
          title: 'Remove person from story',
          confirmLabel: 'Remove from story',
          cancelLabel: 'Cancel',
          destructive: true,
        },
      )
      if (!ok) return

      if (personEditing) {
        cancelPersonEdit()
      }

      const source = row.source === 'user' ? 'user' : 'model'
      const nextOverlay = buildRemovePersonOverlayPatch(draftOverlay, anchor, source)
      const projectSlug =
        typeof catalogProjectSlug === 'string' && catalogProjectSlug.trim()
          ? catalogProjectSlug.trim()
          : ''
      const persistedId = getMergedRowPersistedPersonId(row)
      const stylebookSlug = resolveStylebookSlugForLinkedRow(row, catalogStylebookSlug)

      setSaving(true)
      try {
        if (persistedId && projectSlug) {
          await deleteSavedPerson(persistedId, projectSlug, articleId, stylebookSlug)
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
          'The person was removed from this story. If they were linked in your catalog, check Stylebook candidates to link them again.',
          { title: 'Person removed' },
        )
      } catch (e) {
        showError(
          e instanceof Error ? e.message : 'We could not delete this person. Try again.',
          { title: 'Remove person' },
        )
      } finally {
        setSaving(false)
      }
    },
    [
      showConfirm,
      personEditing,
      cancelPersonEdit,
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
          <h2 className="text-lg font-semibold tracking-tight">Review and edit people</h2>
          <p className="text-sm text-muted-foreground">
            Select a person to highlight their mentions, then choose Edit person to change details.
          </p>
        </div>
        {hasArticleBody ? (
          <Button
            type="button"
            variant={addPersonMode ? 'outline' : 'default'}
            size="sm"
            disabled={addPersonSelection !== null}
            onClick={() => {
              if (addPersonSelection) return
              if (articleTextSelection) {
                handleBeginAddPerson(articleTextSelection)
                return
              }
              if (addPersonMode) {
                cancelAddPersonWorkflow()
                return
              }
              setAddPersonMode(true)
            }}
          >
            {addPersonMode ? null : <Plus className="mr-2 h-4 w-4" />}
            {addPersonMode ? 'Cancel' : 'Add person'}
          </Button>
        ) : null}
      </div>

      {(dirty || fieldsDirty) && !personEditing && (
        <Alert>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
            <span>You have unsaved people review changes.</span>
            <Button type="button" size="sm" disabled={saving} onClick={() => void saveOverlayReview()}>
              Save review
            </Button>
          </AlertDescription>
        </Alert>
      )}

      <div
        className={cn(
          'grid min-h-0 gap-4 lg:grid-cols-2 lg:items-stretch',
          addPersonSelection || personEditing
            ? 'h-[min(52rem,calc(100dvh-10rem))]'
            : 'h-[min(44rem,calc(100dvh-12rem))]',
        )}
      >
        <div
          className={cn(
            'min-h-0 overflow-y-auto rounded-md border p-2.5 text-sm',
            addPersonMode || personEditing
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
              {personEditing ? (
                <p
                  className="mb-2 rounded-md border border-primary/30 bg-primary/10 px-2.5 py-2 text-sm text-foreground"
                  role="status"
                >
                  Highlight to add a mention or quote. Hover and click X to remove.
                </p>
              ) : null}
              {(addPersonMode || awaitingAddPersonReselection) ? (
                <div
                  className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-md border border-primary/30 bg-primary/10 px-2.5 py-2"
                  role="status"
                >
                  <p className="text-sm text-foreground">
                    {awaitingAddPersonReselection
                      ? 'Highlight a new passage in the story for this person.'
                      : 'Highlight the passage in the story that supports this person.'}
                  </p>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 shrink-0 px-2"
                    onClick={() => {
                      if (awaitingAddPersonReselection) {
                        setAwaitingAddPersonReselection(false)
                        setArticleTextSelection(null)
                        window.getSelection()?.removeAllRanges()
                        return
                      }
                      cancelAddPersonWorkflow()
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              ) : null}
              {(selectedAnchor && !addPersonMode && (personEditing || storyMentionHighlightRanges.length > 0 || storyQuoteHighlightRanges.length > 0)) ? (
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
                placeLabels={personLabelsByAnchor}
                interactionMode={articleInteractionMode}
                onSelectPlace={
                  addPersonWorkflowActive || personEditing ? undefined : selectPersonAnchor
                }
                mentionChoicePrompt="Which person?"
                onTextSelectionChange={(selection) => {
                  if (addPersonSelection && !awaitingAddPersonReselection) return
                  setArticleTextSelection(selection)
                  if ((addPersonMode || awaitingAddPersonReselection) && selection) {
                    handleBeginAddPerson(selection)
                  }
                }}
                activeTextSelection={personEditing ? articleTextSelection : null}
                onAddOccurrenceFromSelection={
                  personEditing ? addOccurrenceFromSelection : undefined
                }
                editableOccurrenceClientIds={editableOccurrenceClientIds}
                selectedOccurrenceClientId={selectedOccurrenceClientId}
                onSelectOccurrenceClientId={
                  personEditing ? setSelectedOccurrenceClientId : undefined
                }
                onRemoveOccurrenceClientId={
                  personEditing ? removeOccurrenceClientId : undefined
                }
                className={
                  addPersonMode || awaitingAddPersonReselection || personEditing
                    ? 'cursor-text'
                    : undefined
                }
              />
              {selectedAnchor &&
              !personEditing &&
              storyMentionHighlightRanges.length === 0 &&
              storyQuoteHighlightRanges.length === 0 &&
              article.body.trim().length > 0 ? (
                <p className="mt-2 border-t border-border/60 pt-2 text-xs text-muted-foreground">
                  No matching passage was found in this story for this person.
                </p>
              ) : null}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No story text is available for this item yet.</p>
          )}
        </div>

        {addPersonSelection ? (
          <AddPersonWorkflowPanel
            projectSlug={catalogProjectSlug?.trim() ?? ''}
            runId={runId}
            articleId={articleId ?? 0}
            persistToStylebook={persistAddPersonToStylebook}
            selection={addPersonSelection}
            awaitingNewSelection={awaitingAddPersonReselection}
            onChangeSelection={() => {
              setAwaitingAddPersonReselection(true)
              setArticleTextSelection(null)
              const sel = window.getSelection()
              sel?.removeAllRanges()
            }}
            onCancel={cancelAddPersonWorkflow}
            onCreated={(createdPayload) => {
              void handleAddPersonCreated(createdPayload)
            }}
            onError={(message, title) => showError(message, { title })}
          />
        ) : (
          <ProcessedItemPeopleEditor
            personEditing={personEditing}
            selectedAnchor={selectedAnchor}
            selectedRow={selectedRow}
            rows={displayMergedRows}
            fieldsDraft={fieldsDraft}
            fieldsDirty={fieldsDirty}
            saving={saving}
            onSelectAnchor={selectPersonAnchor}
            onOpenStylebook={handleOpenStylebook}
            onStartEdit={startPersonEdit}
            onCancelEdit={cancelPersonEdit}
            onSaveEdit={() => void handleSavePersonEdit()}
            onDeletePerson={(row) => void handleDeletePerson(row)}
            onUnselect={handleUnselect}
            onFieldsChange={setFieldsDraft}
          />
        )}
      </div>
    </div>
  )
}
