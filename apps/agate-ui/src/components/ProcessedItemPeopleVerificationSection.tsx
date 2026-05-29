import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useAppMessage } from '@/components/AppMessageProvider'
import { ProcessedItemArticleBody } from '@/components/ProcessedItemArticleBody'
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
  applyPersonEditFields,
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
import { resolveProcessedItemArticleId } from '@/lib/review/entities/location/reviewRow'
import {
  applyPersonAnchorPatch,
  buildRemovePersonOverlayPatch,
  normalizeOverlay,
  overlaysStructurallyEqual,
} from '@/lib/review/overlay/verificationOverlay'
import { deleteSavedPerson, updateSavedPerson } from '@/lib/stylebookPeopleApi'
import { cn } from '@/lib/utils'

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
      showMessage('Review saved', { variant: 'success' })
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

  return (
    <div className="space-y-4">
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

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="min-h-[320px]">
          <CardHeader>
            <CardTitle className="text-base">Story</CardTitle>
          </CardHeader>
          <CardContent>
            <ProcessedItemArticleBody body={article?.body ?? ''} highlights={[]} />
          </CardContent>
        </Card>

        <div className="space-y-4">
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
                onSelectAnchor={setSelectedAnchor}
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
      </div>
    </div>
  )
}
