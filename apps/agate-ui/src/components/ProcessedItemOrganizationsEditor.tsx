import { OrganizationsTable } from '@/components/OrganizationsTable'
import { OrganizationEditForm } from '@/components/OrganizationEditForm'
import { Button } from '@/components/ui/button'
import {
  isMergedRowLinkedToStylebook,
  isReviewOnlyMergedOrganizationRow,
} from '@/lib/review/entities/organization/reviewRow'
import type { OrganizationEditFields } from '@/lib/review/entities/organization/organizationEditFields'
import { cn } from '@/lib/utils'
import { List, Loader2, Pencil, Trash2 } from 'lucide-react'

export interface ProcessedItemOrganizationsEditorProps {
  className?: string
  organizationEditing: boolean
  selectedAnchor: string | null
  selectedRow: Record<string, unknown> | null
  rows: Array<Record<string, unknown>>
  fieldsDraft: OrganizationEditFields | undefined
  fieldsDirty: boolean
  saving: boolean
  onSelectAnchor: (anchor: string) => void
  onOpenStylebook: (row: Record<string, unknown>) => void
  onStartEdit: () => void
  onCancelEdit: () => void
  onSaveEdit: () => void
  onDeleteOrganization: (row: Record<string, unknown>) => void
  onUnselect: () => void
  onFieldsChange: (fields: OrganizationEditFields) => void
}

export function ProcessedItemOrganizationsEditor({
  className,
  organizationEditing,
  selectedAnchor,
  selectedRow,
  rows,
  fieldsDraft,
  fieldsDirty,
  saving,
  onSelectAnchor,
  onOpenStylebook,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onDeleteOrganization,
  onUnselect,
  onFieldsChange,
}: ProcessedItemOrganizationsEditorProps) {
  const actionsDisabled = saving
  const reviewOnly = selectedRow !== null && isReviewOnlyMergedOrganizationRow(selectedRow)
  const linkedStylebook = selectedRow !== null && isMergedRowLinkedToStylebook(selectedRow)
  const showToolbar = Boolean(selectedAnchor)

  return (
    <div
      className={cn(
        'flex h-full min-h-0 min-w-0 flex-col gap-2 overflow-hidden rounded-lg border bg-card p-2.5',
        organizationEditing && 'border-primary/40 bg-background',
        className,
      )}
    >
      {showToolbar ? (
      <div className="flex w-full shrink-0 flex-wrap items-center gap-2">
        {selectedAnchor && !organizationEditing ? (
          <>
            <Button
              type="button"
              size="sm"
              className="bg-black text-white hover:bg-black/90"
              disabled={actionsDisabled || !selectedRow}
              onClick={onStartEdit}
            >
              <Pencil className="mr-2 h-4 w-4" />
              Edit
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={actionsDisabled || !selectedRow}
              onClick={() => {
                if (selectedRow) onDeleteOrganization(selectedRow)
              }}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={actionsDisabled}
              onClick={onUnselect}
            >
              <List className="mr-2 h-4 w-4" />
              Unselect
            </Button>
          </>
        ) : null}
        {organizationEditing && selectedAnchor ? (
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={actionsDisabled}
              onClick={onCancelEdit}
            >
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={!fieldsDirty || actionsDisabled}
              onClick={onSaveEdit}
            >
              {saving ? (
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
      ) : null}

      {organizationEditing ? (
        <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-1.5">
          {linkedStylebook ? (
            <p className="text-xs text-muted-foreground">
              Edits here do not affect this organization&apos;s canonical record in Stylebook.
            </p>
          ) : null}
          {reviewOnly ? (
            <p className="text-xs text-muted-foreground">
              These changes are saved with this review only until the organization is saved for this
              story.
            </p>
          ) : null}
          {fieldsDraft ? (
            <>
              <p className="text-xs text-muted-foreground">
                {fieldsDraft.occurrences.filter((o) => !o.suppressed && !o.isQuote).length} mention
                {fieldsDraft.occurrences.filter((o) => !o.suppressed && !o.isQuote).length !== 1
                  ? 's'
                  : ''}
                ,{' '}
                {fieldsDraft.occurrences.filter((o) => !o.suppressed && o.isQuote).length} quote
                {fieldsDraft.occurrences.filter((o) => !o.suppressed && o.isQuote).length !== 1
                  ? 's'
                  : ''}{' '}
                in the story. Edit them in the story pane.
              </p>
              <OrganizationEditForm fields={fieldsDraft} disabled={saving} onChange={onFieldsChange} />
            </>
          ) : null}
        </div>
      ) : (
        <div
          className={cn(
            'flex min-h-0 min-w-0 flex-1 flex-col gap-1 overflow-hidden',
            selectedAnchor && 'border-t border-border pt-2',
          )}
        >
          <h4 className="shrink-0 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Organizations
          </h4>
          <OrganizationsTable
            rows={rows}
            selectedAnchor={selectedAnchor}
            onSelectAnchor={onSelectAnchor}
            onOpenStylebook={onOpenStylebook}
            onDeleteOrganization={onDeleteOrganization}
            deleteDisabled={actionsDisabled}
          />
        </div>
      )}
    </div>
  )
}
