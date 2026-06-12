import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAppMessage } from '@/components/AppMessageProvider'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { ProcessedItem } from '@/lib/api'
import { patchProcessedItemArticleMetaCategory } from '@/lib/api'
import {
  articleMetaTypeLabel,
  type ProcessedItemArticleMetaRow,
} from '@/lib/review/content/articleMetaDisplay'
import { Loader2, Pencil, Save } from 'lucide-react'

export type ProcessedItemMetaVerificationSectionProps = {
  runId: string
  item: ProcessedItem
  onItemUpdated: (item: ProcessedItem) => void
  onVerificationDirtyChange?: (dirty: boolean) => void
  reviewLocked?: boolean
}

type RowDraft = {
  category: string
  baselineCategory: string
}

function confidenceLabel(value: number): string {
  if (!Number.isFinite(value)) return '—'
  return value.toFixed(2)
}

export function ProcessedItemMetaVerificationSection({
  runId,
  item,
  onItemUpdated,
  onVerificationDirtyChange,
  reviewLocked = false,
}: ProcessedItemMetaVerificationSectionProps) {
  const { showError, showMessage } = useAppMessage()
  const rows = useMemo(() => item.article_meta ?? [], [item.article_meta])
  const [editMode, setEditMode] = useState(false)
  const [drafts, setDrafts] = useState<Record<number, RowDraft>>({})
  const [savingId, setSavingId] = useState<number | null>(null)

  useEffect(() => {
    const next: Record<number, RowDraft> = {}
    for (const row of rows) {
      next[row.id] = { category: row.category, baselineCategory: row.category }
    }
    setDrafts(next)
  }, [item.id, item.overlay_version, rows])

  const dirty = useMemo(() => {
    return rows.some((row) => {
      const draft = drafts[row.id]
      return draft != null && draft.category.trim() !== draft.baselineCategory.trim()
    })
  }, [drafts, rows])

  useEffect(() => {
    onVerificationDirtyChange?.(dirty)
  }, [dirty, onVerificationDirtyChange])

  const handleSaveRow = useCallback(
    async (row: ProcessedItemArticleMetaRow) => {
      const draft = drafts[row.id]
      if (!draft) return
      const category = draft.category.trim()
      if (!category) {
        showError('Category cannot be empty.')
        return
      }
      if (category === draft.baselineCategory.trim()) return

      setSavingId(row.id)
      try {
        const updated = await patchProcessedItemArticleMetaCategory(
          runId,
          item.id,
          row.id,
          category,
          item.overlay_version,
        )
        onItemUpdated(updated)
        showMessage('Category updated.')
        setEditMode(false)
      } catch (error) {
        showError(error instanceof Error ? error.message : 'Could not save category.')
      } finally {
        setSavingId(null)
      }
    },
    [drafts, item.id, item.overlay_version, onItemUpdated, runId, showError, showMessage],
  )

  if (rows.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          No article metadata tags were assigned for this story yet. Run a flow with Article
          Metadata to classify this story.
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Tags assigned by your flow. You can adjust the category label; rationale and confidence
          stay as the model produced them.
        </p>
        {!reviewLocked ? (
          <Button
            type="button"
            variant={editMode ? 'secondary' : 'outline'}
            size="sm"
            onClick={() => setEditMode((value) => !value)}
          >
            <Pencil className="mr-2 h-4 w-4" />
            {editMode ? 'Done editing' : 'Edit categories'}
          </Button>
        ) : null}
      </div>

      {rows.map((row) => {
        const draft = drafts[row.id]
        const rowDirty =
          draft != null && draft.category.trim() !== draft.baselineCategory.trim()
        return (
          <Card key={row.id}>
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-medium">
                {articleMetaTypeLabel(row.meta_type)}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor={`meta-category-${row.id}`}>Category</Label>
                {editMode && !reviewLocked ? (
                  <Input
                    id={`meta-category-${row.id}`}
                    value={draft?.category ?? row.category}
                    onChange={(event) => {
                      const value = event.target.value
                      setDrafts((current) => ({
                        ...current,
                        [row.id]: {
                          category: value,
                          baselineCategory: current[row.id]?.baselineCategory ?? row.category,
                        },
                      }))
                    }}
                  />
                ) : (
                  <p className="text-sm font-medium">{row.category}</p>
                )}
                {row.source === 'review' ? (
                  <p className="text-xs text-muted-foreground">Edited in review</p>
                ) : null}
              </div>

              <div className="space-y-1">
                <Label>Rationale</Label>
                <p className="text-sm text-muted-foreground leading-relaxed">{row.rationale}</p>
              </div>

              <div className="space-y-1">
                <Label>Confidence</Label>
                <p className="text-sm text-muted-foreground">{confidenceLabel(row.confidence)}</p>
              </div>

              {editMode && !reviewLocked && rowDirty ? (
                <Button
                  type="button"
                  size="sm"
                  disabled={savingId === row.id}
                  onClick={() => void handleSaveRow(row)}
                >
                  {savingId === row.id ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="mr-2 h-4 w-4" />
                  )}
                  Save category
                </Button>
              ) : null}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
