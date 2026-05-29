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
import { PeopleTable } from '@/components/PeopleTable'
import { PersonEditForm } from '@/components/PersonEditForm'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Graph, ProcessedItem } from '@/lib/api'
import { getProcessedItem, patchProcessedItemOverlay } from '@/lib/api'
import {
  stylebookPeopleCandidatesHref,
  stylebookPersonCanonicalDetailHref,
} from '@/lib/platformUrls'
import {
  buildOccurrenceSpanHits,
  findAllMentionOccurrencesInArticle,
  resolveEvidenceSpansInArticle,
} from '@/lib/review/content/evidenceSpan'
import { readMentionOccurrencesFromRow } from '@/lib/review/entities/location/mentionOccurrences'
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
  isMergedRowLinkedToStylebook,
  readPersonFromRow,
} from '@/lib/review/entities/person/reviewRow'
import {
  appendUserAddedPersonToOverlay,
  applyPersonAnchorPatch,
  buildRemovePersonOverlayPatch,
  buildUserAddedPersonOverlayRow,
  normalizeOverlay,
  overlaysStructurallyEqual,
} from '@/lib/review/overlay/verificationOverlay'
import { deleteSavedPerson, updateSavedPerson } from '@/lib/stylebookPeopleApi'
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
  const [selectedAnchor, setSelectedAnchor] = useState<string | null>(null)
  const [fieldsDraft, setFieldsDraft] = useState<PersonEditFields | undefined>(undefined)
  const [fieldsBaseline, setFieldsBaseline] = useState<PersonEditFields | undefined>(undefined)
  const [addPersonMode, setAddPersonMode] = useState(false)
  const [addPersonSelection, setAddPersonSelection] = useState<ArticleTextSelection | null>(null)
  const [articleTextSelection, setArticleTextSelection] = useState<ArticleTextSelection | null>(null)
  const lastItemSyncKeyRef = useRef('')

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

  useEffect(() => {
    if (!selectedRow) {
      setFieldsDraft(undefined)
      setFieldsBaseline(undefined)
      return
    }
    const fields = readPersonEditFields(readPersonFromRow(selectedRow))
    setFieldsDraft(fields)
    setFieldsBaseline(fields)
  }, [selectedRow?.anchor])

  const fieldsDirty =
    fieldsDraft !== undefined &&
    fieldsBaseline !== undefined &&
    !personEditFieldsEqual(fieldsDraft, fieldsBaseline)

  const storyHighlightResult = useMemo(() => {
    const body = typeof article?.body === 'string' ? article.body : ''
    if (!selectedAnchor) {
      return resolveEvidenceSpansInArticle(body, undefined)
    }
    const row = displayMergedRows.find((r) => getMergedRowAnchor(r) === selectedAnchor)
    if (!row) {
      return resolveEvidenceSpansInArticle(body, undefined)
    }
    const occurrences = readMentionOccurrencesFromRow({
      location: readPersonFromRow(row),
      mention_occurrences: row.mention_occurrences,
    })
    const active = occurrences.filter((o) => !o.suppressed && o.mentionText.trim())
    if (active.length > 0 && body) {
      const ranges = buildOccurrenceSpanHits(body, [
        {
          anchor: selectedAnchor,
          occurrences: active.map((o) => ({
            clientId: o.clientId,
            mentionText: o.mentionText,
            startChar: o.startChar,
            endChar: o.endChar,
            suppressed: o.suppressed,
          })),
        },
      ]).map(({ start, end }) => ({ start, end }))
      if (ranges.length > 0) {
        return { kind: 'ranges' as const, ranges }
      }
    }
    return resolveEvidenceSpansInArticle(body, readPersonFromRow(row))
  }, [article?.body, selectedAnchor, displayMergedRows])

  const storyHighlightRanges =
    storyHighlightResult.kind === 'ranges' ? storyHighlightResult.ranges : []

  const activeStoryHighlightRanges = useMemo(
    () =>
      addPersonSelection
        ? [
            ...storyHighlightRanges,
            { start: addPersonSelection.start, end: addPersonSelection.end },
          ]
        : storyHighlightRanges,
    [addPersonSelection, storyHighlightRanges],
  )

  const ambientHighlightRanges = useMemo(() => {
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
  }, [article?.body, displayMergedRows])

  const selectPersonAnchor = useCallback((anchor: string) => {
    setAddPersonMode(false)
    setAddPersonSelection(null)
    setSelectedAnchor(anchor)
  }, [])

  const handleBeginAddPerson = useCallback((selection: ArticleTextSelection) => {
    setAddPersonMode(false)
    setSelectedAnchor(null)
    setAddPersonSelection(selection)
    setArticleTextSelection(null)
  }, [])

  const exitAddPersonMode = useCallback(() => {
    setAddPersonMode(false)
    setArticleTextSelection(null)
    const sel = window.getSelection()
    sel?.removeAllRanges()
  }, [])

  useEffect(() => {
    if (!addPersonMode) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') exitAddPersonMode()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [addPersonMode, exitAddPersonMode])

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
          { overlay: nextOverlay },
          item.overlay_version ?? 0,
        )
        onItemUpdated(updated)
        setBaselineOverlay(normalizeOverlay(updated.overlay))
        setDraftOverlay(normalizeOverlay(updated.overlay))
        setAddPersonSelection(null)
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

  const handleSave = useCallback(async () => {
    if (saving) return
    setSaving(true)
    try {
      let nextOverlay = draftOverlay
      if (selectedAnchor && fieldsDraft) {
        nextOverlay = applyPersonAnchorPatch(
          nextOverlay,
          selectedAnchor,
          buildPersonEditOverlayPatch(fieldsDraft),
        )
        setDraftOverlay(nextOverlay)
      }
      const persistedId = selectedRow ? getMergedRowPersistedPersonId(selectedRow) : null
      if (persistedId && fieldsDraft && catalogProjectSlug) {
        await updateSavedPerson(
          persistedId,
          catalogProjectSlug,
          {
            name: fieldsDraft.name,
            title: fieldsDraft.title,
            affiliation: fieldsDraft.affiliation,
            person_type: fieldsDraft.personType,
            role_in_story: fieldsDraft.roleInStory,
            nature: fieldsDraft.nature,
            public_figure: fieldsDraft.publicFigure,
          },
          articleId,
        )
      }
      const updated = await patchProcessedItemOverlay(
        runId,
        item.id,
        { overlay: nextOverlay },
        item.overlay_version ?? 0,
      )
      onItemUpdated(updated)
      setBaselineOverlay(normalizeOverlay(updated.overlay))
      setDraftOverlay(normalizeOverlay(updated.overlay))
      if (fieldsDraft) setFieldsBaseline(fieldsDraft)
      showMessage('Review saved', { title: 'People review' })
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Save failed', { title: 'People review' })
    } finally {
      setSaving(false)
    }
  }, [
    saving,
    draftOverlay,
    selectedAnchor,
    fieldsDraft,
    selectedRow,
    catalogProjectSlug,
    articleId,
    runId,
    item.id,
    item.overlay_version,
    onItemUpdated,
    showError,
    showMessage,
  ])

  const handleOpenStylebook = useCallback(
    (row: Record<string, unknown>) => {
      if (dirty || fieldsDirty) {
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
    [dirty, fieldsDirty, catalogStylebookSlug, catalogProjectSlug, showError],
  )

  const handleDeletePerson = useCallback(
    async (row: Record<string, unknown>) => {
      const anchor = getMergedRowAnchor(row)
      if (!anchor) return
      const ok = await showConfirm('Remove this person from the story review?', {
        title: 'Remove person',
        confirmLabel: 'Remove',
      })
      if (!ok) return
      setSaving(true)
      try {
        const source = row.source === 'user' ? 'user' : 'model'
        const nextOverlay = buildRemovePersonOverlayPatch(draftOverlay, anchor, source)
        const persistedId = getMergedRowPersistedPersonId(row)
        if (persistedId && catalogProjectSlug) {
          await deleteSavedPerson(persistedId, catalogProjectSlug, articleId)
        }
        const updated = await patchProcessedItemOverlay(
          runId,
          item.id,
          { overlay: nextOverlay },
          item.overlay_version ?? 0,
        )
        onItemUpdated(updated)
        setBaselineOverlay(normalizeOverlay(updated.overlay))
        setDraftOverlay(normalizeOverlay(updated.overlay))
        if (selectedAnchor === anchor) setSelectedAnchor(null)
      } catch (err) {
        showError(err instanceof Error ? err.message : 'Remove failed', { title: 'People review' })
      } finally {
        setSaving(false)
      }
    },
    [
      showConfirm,
      draftOverlay,
      catalogProjectSlug,
      articleId,
      runId,
      item.id,
      item.overlay_version,
      onItemUpdated,
      selectedAnchor,
      showError,
    ],
  )

  const refreshItem = useCallback(async () => {
    const updated = await getProcessedItem(runId, item.id)
    onItemUpdated(updated)
  }, [runId, item.id, onItemUpdated])

  const linkedReadOnly =
    selectedRow !== null && isMergedRowLinkedToStylebook(selectedRow) && !fieldsDirty

  const canAddPerson = Boolean(article?.body?.trim()) && !addPersonSelection

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Review and edit people</h2>
          <p className="text-sm text-muted-foreground">
            Select a person to highlight their mentions in the story and edit details.
          </p>
        </div>
        {canAddPerson ? (
          <Button
            type="button"
            variant={addPersonMode ? 'secondary' : 'default'}
            size="sm"
            onClick={() => {
              if (addPersonSelection) return
              if (articleTextSelection) {
                handleBeginAddPerson(articleTextSelection)
                return
              }
              if (addPersonMode) {
                exitAddPersonMode()
                return
              }
              setAddPersonMode(true)
            }}
          >
            {addPersonMode ? null : <Plus className="mr-2 h-4 w-4" />}
            {addPersonMode ? 'Cancel adding person' : 'Add person'}
          </Button>
        ) : null}
      </div>

      {(dirty || fieldsDirty) && (
        <Alert>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2">
            <span>You have unsaved people review changes.</span>
            <Button type="button" size="sm" disabled={saving} onClick={() => void handleSave()}>
              Save review
            </Button>
          </AlertDescription>
        </Alert>
      )}

      <div
        className={cn(
          'grid min-h-0 gap-4 lg:grid-cols-2 lg:items-stretch',
          addPersonSelection ? 'h-[min(52rem,calc(100dvh-10rem))]' : 'h-[min(44rem,calc(100dvh-12rem))]',
        )}
      >
        <div
          className={cn(
            'min-h-0 overflow-y-auto rounded-md border p-2.5 text-sm',
            addPersonMode
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
              {addPersonMode ? (
                <p
                  className="mb-2 rounded-md border border-primary/30 bg-primary/10 px-2.5 py-2 text-sm text-foreground"
                  role="status"
                >
                  Highlight the passage in the story that supports this person.
                </p>
              ) : null}
              <ProcessedItemArticleBody
                body={article.body}
                ambientHighlights={ambientHighlightRanges}
                highlights={activeStoryHighlightRanges}
                scrollWhenKey={selectedAnchor}
                onTextSelectionChange={(selection) => {
                  if (addPersonSelection) return
                  setArticleTextSelection(selection)
                  if (addPersonMode && selection) {
                    handleBeginAddPerson(selection)
                  }
                }}
                className={addPersonMode ? 'cursor-text' : undefined}
              />
              {selectedAnchor &&
              storyHighlightRanges.length === 0 &&
              storyHighlightResult.kind === 'none' &&
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
            onChangeSelection={() => {
              setAddPersonSelection(null)
              setArticleTextSelection(null)
              setAddPersonMode(true)
            }}
            onCancel={() => {
              setAddPersonSelection(null)
              setArticleTextSelection(null)
              setAddPersonMode(false)
            }}
            onCreated={(createdPayload) => {
              void handleAddPersonCreated(createdPayload)
            }}
            onError={(message, title) => showError(message, { title })}
          />
        ) : (
          <div className="min-h-0 space-y-4 overflow-y-auto">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between gap-2">
                <CardTitle className="text-base">People</CardTitle>
                <Button type="button" variant="outline" size="sm" onClick={() => void refreshItem()}>
                  Refresh
                </Button>
              </CardHeader>
              <CardContent>
                <PeopleTable
                  rows={displayMergedRows}
                  selectedAnchor={selectedAnchor}
                  onSelectAnchor={selectPersonAnchor}
                  onOpenStylebook={handleOpenStylebook}
                  onDeletePerson={(row) => void handleDeletePerson(row)}
                  deleteDisabled={saving}
                />
              </CardContent>
            </Card>

            {selectedRow && fieldsDraft ? (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Edit person</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {linkedReadOnly ? (
                    <p className="text-sm text-muted-foreground">
                      This person is linked to a Stylebook canonical. Open Stylebook to edit the
                      catalog record.
                    </p>
                  ) : null}
                  <PersonEditForm
                    fields={fieldsDraft}
                    disabled={saving || linkedReadOnly}
                    onChange={setFieldsDraft}
                  />
                  <div className="flex justify-end gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      disabled={saving || !fieldsDirty}
                      onClick={() => fieldsBaseline && setFieldsDraft(fieldsBaseline)}
                    >
                      Reset
                    </Button>
                    <Button
                      type="button"
                      disabled={saving || (!fieldsDirty && !dirty)}
                      onClick={() => void handleSave()}
                    >
                      Save
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className={cn('py-10 text-center text-sm text-muted-foreground')}>
                  Select a person to edit details.
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
