import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useBlocker } from 'react-router-dom'
import { useAppMessage } from '@/components/AppMessageProvider'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import type { Graph, ProcessedItem } from '@/lib/api'
import { getProcessedItem, patchProcessedItemOverlay } from '@/lib/api'
import {
  applyDescriptionPatch,
  getLocationDescription,
  getMergedRowAnchor,
  isApiConflictError,
  isLocationLinkedToStylebookCanonical,
  normalizeOverlay,
  overlaysStructurallyEqual,
} from '@/lib/processedItemVerificationOverlay'
import { Loader2, MapPin } from 'lucide-react'

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
}

export function ProcessedItemVerificationSection({
  runId,
  item,
  graph,
  onItemUpdated,
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
  }, [item.overlay, item.overlay_version, item.id, runId, syncKey, dirty])

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty &&
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search),
  )

  const blockerConfirmOpenRef = useRef(false)

  useEffect(() => {
    if (blocker.state !== 'blocked') {
      blockerConfirmOpenRef.current = false
      return
    }
    if (blockerConfirmOpenRef.current) {
      return
    }
    blockerConfirmOpenRef.current = true
    void showConfirm(
      'Save your changes before leaving, or stay on this page to keep editing.',
      {
        title: 'Unsaved changes',
        confirmLabel: 'Leave without saving',
        cancelLabel: 'Stay',
        destructive: true,
      },
    ).then((leave) => {
      if (leave) {
        blocker.proceed()
      } else {
        blocker.reset()
      }
      blockerConfirmOpenRef.current = false
    })
  }, [blocker, showConfirm])

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
  const article = item.article_context

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
                <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground">
                  {article?.body?.trim()
                    ? article.body
                    : 'No story text is available for this item yet.'}
                </pre>
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
                      className="rounded-md border p-3 space-y-2 bg-card"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="secondary">{source}</Badge>
                        {nodeLabel ? (
                          <span className="text-xs text-muted-foreground truncate max-w-[12rem]">
                            {nodeLabel}
                          </span>
                        ) : null}
                        {row.stale === true ? (
                          <Badge variant="outline" className="text-amber-800 border-amber-300">
                            Needs review
                          </Badge>
                        ) : null}
                      </div>
                      {linked ? (
                        <>
                          <p className="text-sm text-foreground">{displayDescription || '—'}</p>
                          <p className="text-xs text-muted-foreground">
                            This place is linked to your catalog. Edit the catalog entry there if the
                            official name or details need to change.
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

        <Alert>
          <AlertDescription className="flex items-start gap-2">
            <MapPin className="h-4 w-4 shrink-0 mt-0.5" aria-hidden />
            <span>
              Map view and sentence highlights will appear here in a later update. Place descriptions can
              still be saved above.
            </span>
          </AlertDescription>
        </Alert>
      </CardContent>
    </Card>
  )
}
