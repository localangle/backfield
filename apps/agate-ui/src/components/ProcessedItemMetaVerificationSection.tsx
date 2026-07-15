import { useCallback, useEffect, useMemo, useState } from 'react'
import { ProcessedItemEditorReviewBanner } from '@/components/ProcessedItemEditorReviewBanner'
import { useAppMessage } from '@/components/AppMessageProvider'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { ProcessedItem } from '@/lib/api'
import {
  createProcessedItemArticleMeta,
  deleteProcessedItemArticleMeta,
  patchProcessedItemArticleMetaCategory,
} from '@/lib/api'
import {
  articleMetaTypeLabel,
  type ProcessedItemArticleMetaRow,
} from '@/lib/review/content/articleMetaDisplay'
import {
  ARTICLE_METADATA_PRESET_OPTIONS,
  type ArticleMetadataPresetId,
} from '@/nodes/article_metadata/presetOptions'
import { Loader2, Pencil, Plus, Save, Trash2 } from 'lucide-react'

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
  const { showError, showMessage, showConfirm } = useAppMessage()
  const rows = useMemo(() => item.article_meta ?? [], [item.article_meta])
  const [editMode, setEditMode] = useState(false)
  const [drafts, setDrafts] = useState<Record<number, RowDraft>>({})
  const [savingId, setSavingId] = useState<number | null>(null)
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [addPreset, setAddPreset] = useState<ArticleMetadataPresetId>('subject')
  const [addCustomType, setAddCustomType] = useState('')
  const [addCategory, setAddCategory] = useState('')
  const [adding, setAdding] = useState(false)

  const usedMetaTypes = useMemo(
    () => new Set(rows.map((row) => row.meta_type.trim().toLowerCase())),
    [rows],
  )

  const availablePresets = useMemo(
    () =>
      ARTICLE_METADATA_PRESET_OPTIONS.filter((option) => {
        if (option.id === 'custom') return true
        return !usedMetaTypes.has(option.id)
      }),
    [usedMetaTypes],
  )

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

  const [deletingId, setDeletingId] = useState<number | null>(null)

  const resetAddForm = useCallback(() => {
    const defaultPreset =
      availablePresets.find((option) => option.id !== 'custom')?.id ??
      availablePresets[0]?.id ??
      'subject'
    setAddPreset(defaultPreset)
    setAddCustomType('')
    setAddCategory('')
  }, [availablePresets])

  const handleOpenAddDialog = useCallback(() => {
    resetAddForm()
    setAddDialogOpen(true)
  }, [resetAddForm])

  const handleAddTag = useCallback(async () => {
    const category = addCategory.trim()
    if (!category) {
      showError('Enter a category label for this tag.')
      return
    }

    let metaType: string = addPreset
    let promptPreset: string | undefined = addPreset
    if (addPreset === 'custom') {
      metaType = addCustomType.trim().toLowerCase().replace(/-/g, '_')
      if (!metaType) {
        showError('Enter a name for your custom tag type.')
        return
      }
      promptPreset = 'custom'
    }

    if (usedMetaTypes.has(metaType)) {
      showError('This story already has a tag of that type.')
      return
    }

    setAdding(true)
    try {
      const updated = await createProcessedItemArticleMeta(
        runId,
        item.id,
        {
          meta_type: metaType,
          category,
          prompt_preset: promptPreset,
        },
        item.overlay_version ?? 0,
      )
      onItemUpdated(updated)
      showMessage('Tag added.')
      setAddDialogOpen(false)
      setEditMode(false)
    } catch (error) {
      showError(error instanceof Error ? error.message : 'Could not add tag.')
    } finally {
      setAdding(false)
    }
  }, [
    addCategory,
    addCustomType,
    addPreset,
    item.id,
    item.overlay_version,
    onItemUpdated,
    runId,
    showError,
    showMessage,
    usedMetaTypes,
  ])

  const handleDeleteRow = useCallback(
    async (row: ProcessedItemArticleMetaRow) => {
      const label = articleMetaTypeLabel(row.meta_type)
      const ok = await showConfirm(
        `Remove the “${label}” tag from this story? You can rerun the flow later if you need it again.`,
        {
          title: 'Remove tag',
          confirmLabel: 'Remove tag',
          cancelLabel: 'Cancel',
          destructive: true,
        },
      )
      if (!ok) return

      setDeletingId(row.id)
      try {
        const updated = await deleteProcessedItemArticleMeta(
          runId,
          item.id,
          row.id,
          item.overlay_version ?? 0,
        )
        onItemUpdated(updated)
        showMessage('Tag removed.')
        setEditMode(false)
      } catch (error) {
        showError(error instanceof Error ? error.message : 'Could not remove tag.')
      } finally {
        setDeletingId(null)
      }
    },
    [item.id, item.overlay_version, onItemUpdated, runId, showConfirm, showError, showMessage],
  )

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
          item.overlay_version ?? 0,
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

  const canAddTag = !reviewLocked && availablePresets.length > 0

  const addTagButton = canAddTag ? (
    <Button type="button" variant="outline" size="sm" onClick={handleOpenAddDialog}>
      <Plus className="mr-2 h-4 w-4" />
      Add tag
    </Button>
  ) : null

  if (rows.length === 0) {
    return (
      <div className="space-y-4">
        <ProcessedItemEditorReviewBanner item={item} section="meta" />
        <Card>
          <CardContent className="space-y-4 py-10 text-center">
            <p className="text-sm text-muted-foreground">
              No tags yet. Add tags manually or run a flow with Article Metadata to classify this
              story.
            </p>
            {addTagButton ? <div>{addTagButton}</div> : null}
          </CardContent>
        </Card>

        <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Add tag</DialogTitle>
              <DialogDescription>
                Choose a tag type and category label. You can add more than one tag type per story.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="meta-add-preset-empty">Tag type</Label>
                <Select
                  value={addPreset}
                  onValueChange={(value) => setAddPreset(value as ArticleMetadataPresetId)}
                >
                  <SelectTrigger id="meta-add-preset-empty">
                    <SelectValue placeholder="Choose tag type" />
                  </SelectTrigger>
                  <SelectContent>
                    {availablePresets.map((option) => (
                      <SelectItem key={option.id} value={option.id}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {addPreset === 'custom' ? (
                <div className="space-y-2">
                  <Label htmlFor="meta-add-custom-type-empty">Custom tag name</Label>
                  <Input
                    id="meta-add-custom-type-empty"
                    value={addCustomType}
                    onChange={(event) => setAddCustomType(event.target.value)}
                    placeholder="e.g. editorial_tone"
                  />
                </div>
              ) : null}
              <div className="space-y-2">
                <Label htmlFor="meta-add-category-empty">Category</Label>
                <Input
                  id="meta-add-category-empty"
                  value={addCategory}
                  onChange={(event) => setAddCategory(event.target.value)}
                  placeholder="e.g. Local news"
                />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setAddDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="button" disabled={adding} onClick={() => void handleAddTag()}>
                {adding ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                Add tag
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <ProcessedItemEditorReviewBanner item={item} section="meta" />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Tags assigned by your flow or added in review. You can adjust category labels, add tags,
          or remove tags you do not want.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          {addTagButton}
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

              {!reviewLocked ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={deletingId === row.id || savingId === row.id}
                  onClick={() => void handleDeleteRow(row)}
                >
                  {deletingId === row.id ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="mr-2 h-4 w-4" />
                  )}
                  Remove tag
                </Button>
              ) : null}
            </CardContent>
          </Card>
        )
      })}

      <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add tag</DialogTitle>
            <DialogDescription>
              Choose a tag type and category label. Each tag type can appear once per story.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="meta-add-preset">Tag type</Label>
              <Select
                value={addPreset}
                onValueChange={(value) => setAddPreset(value as ArticleMetadataPresetId)}
              >
                <SelectTrigger id="meta-add-preset">
                  <SelectValue placeholder="Choose tag type" />
                </SelectTrigger>
                <SelectContent>
                  {availablePresets.map((option) => (
                    <SelectItem key={option.id} value={option.id}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {addPreset === 'custom' ? (
              <div className="space-y-2">
                <Label htmlFor="meta-add-custom-type">Custom tag name</Label>
                <Input
                  id="meta-add-custom-type"
                  value={addCustomType}
                  onChange={(event) => setAddCustomType(event.target.value)}
                  placeholder="e.g. editorial_tone"
                />
              </div>
            ) : null}
            <div className="space-y-2">
              <Label htmlFor="meta-add-category">Category</Label>
              <Input
                id="meta-add-category"
                value={addCategory}
                onChange={(event) => setAddCategory(event.target.value)}
                placeholder="e.g. Local news"
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setAddDialogOpen(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={adding} onClick={() => void handleAddTag()}>
              {adding ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Add tag
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
