import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Pencil, Plus, Trash2, X } from 'lucide-react'
import { useAppMessage } from '@/components/AppMessageProvider'
import {
  ProcessedItemArticleBody,
  type ArticleTextSelection,
} from '@/components/ProcessedItemArticleBody'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { patchProcessedItemOverlay, type ProcessedItem } from '@/lib/api'
import {
  buildCustomRecordTables,
  customAmbientHighlightRanges,
  customMentionHighlightRanges,
  customRecordCellListItems,
  customRecordCellText,
  type CustomRecordColumn,
  type CustomRecordMentionDisplay,
  type CustomRecordRow,
  type CustomRecordTableModel,
} from '@/lib/review/content/customRecordsDisplay'
import {
  applyCustomRecordFieldsPatch,
  applyCustomRecordMentionsPatch,
  applyCustomRecordsOverlayToTables,
  appendUserAddedCustomRecord,
  buildRemoveCustomRecordPatch,
  newUserAddedRecordKey,
  patchUserAddedCustomRecord,
} from '@/lib/review/entities/custom/customRecordsOverlay'
import {
  isApiConflictError,
  overlaysStructurallyEqual,
} from '@/lib/review/overlay/verificationOverlay'
import { cn } from '@/lib/utils'

export type ProcessedItemCustomRecordsSectionProps = {
  runId: string | number
  item: ProcessedItem
  onItemUpdated?: (item: ProcessedItem) => void
  onVerificationDirtyChange?: (dirty: boolean) => void
  /** When a rerun is in flight; custom records cannot be edited. */
  reviewLocked?: boolean
}

type SelectedMention = {
  recordKey: string
  mentionIndex: number
}

type MentionTarget = {
  recordType: string
  recordKey: string
}

function cloneOverlay(overlay: Record<string, unknown> | null | undefined): Record<string, unknown> {
  if (!overlay || typeof overlay !== 'object' || Array.isArray(overlay)) return {}
  return JSON.parse(JSON.stringify(overlay)) as Record<string, unknown>
}

function confidenceLabel(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—'
  return value.toFixed(2)
}

function blankFieldsForColumns(columns: CustomRecordColumn[]): Record<string, unknown> {
  const fields: Record<string, unknown> = {}
  for (const column of columns) {
    if (column.type === 'string_list') {
      fields[column.name] = []
    } else if (column.type === 'string' || column.type === 'date') {
      fields[column.name] = ''
    } else {
      fields[column.name] = null
    }
  }
  return fields
}

function FieldCell({ value }: { value: unknown }) {
  const listItems = customRecordCellListItems(value)
  if (listItems) {
    return (
      <div className="flex flex-wrap gap-1">
        {listItems.map((entry, index) => (
          <span
            key={`${entry}-${index}`}
            className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs"
          >
            {entry}
          </span>
        ))}
      </div>
    )
  }
  return <span>{customRecordCellText(value)}</span>
}

function StringListEditor({
  value,
  onCommit,
}: {
  value: unknown
  onCommit: (next: string[]) => void
}) {
  const items = useMemo(
    () => (Array.isArray(value) ? value.map((entry) => String(entry)) : []),
    [value],
  )
  const [pending, setPending] = useState('')

  const addPending = () => {
    const entry = pending.trim()
    if (!entry) return
    onCommit([...items, entry])
    setPending('')
  }

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap gap-1">
        {items.map((entry, index) => (
          <span
            key={`${entry}-${index}`}
            className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs"
          >
            {entry}
            <button
              type="button"
              aria-label={`Remove ${entry}`}
              className="cursor-pointer text-muted-foreground hover:text-foreground"
              onClick={() => onCommit(items.filter((_, i) => i !== index))}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
      </div>
      <Input
        value={pending}
        placeholder="Add an entry"
        className="h-7 text-xs"
        onChange={(e) => setPending(e.target.value)}
        onBlur={addPending}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault()
            addPending()
          }
        }}
      />
    </div>
  )
}

/** Text/number editor with local state that commits on blur or Enter. */
function CommitOnBlurInput({
  initialValue,
  inputType,
  onCommit,
}: {
  initialValue: string
  inputType: 'text' | 'number'
  onCommit: (raw: string) => void
}) {
  const [value, setValue] = useState(initialValue)

  useEffect(() => {
    setValue(initialValue)
  }, [initialValue])

  return (
    <Input
      value={value}
      type={inputType}
      className="h-8 min-w-[7rem] text-sm"
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => onCommit(value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          onCommit(value)
        }
      }}
    />
  )
}

function FieldEditor({
  column,
  value,
  onCommit,
}: {
  column: CustomRecordColumn
  value: unknown
  onCommit: (next: unknown) => void
}) {
  if (column.type === 'boolean') {
    const current = value === true ? 'yes' : value === false ? 'no' : 'unset'
    return (
      <Select
        value={current}
        onValueChange={(next) => onCommit(next === 'yes' ? true : next === 'no' ? false : null)}
      >
        <SelectTrigger className="h-8 w-[6.5rem] text-sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="yes">Yes</SelectItem>
          <SelectItem value="no">No</SelectItem>
          <SelectItem value="unset">—</SelectItem>
        </SelectContent>
      </Select>
    )
  }
  if (column.type === 'date') {
    return (
      <Input
        type="date"
        value={typeof value === 'string' ? value : ''}
        className="h-8 w-[10rem] text-sm"
        onChange={(e) => onCommit(e.target.value || null)}
      />
    )
  }
  if (column.type === 'string_list') {
    return <StringListEditor value={value} onCommit={(next) => onCommit(next)} />
  }
  if (column.type === 'number') {
    const initial = typeof value === 'number' && Number.isFinite(value) ? String(value) : ''
    return (
      <CommitOnBlurInput
        initialValue={initial}
        inputType="number"
        onCommit={(raw) => {
          const trimmed = raw.trim()
          if (!trimmed) {
            onCommit(null)
            return
          }
          const parsed = Number(trimmed)
          onCommit(Number.isFinite(parsed) ? parsed : null)
        }}
      />
    )
  }
  return (
    <CommitOnBlurInput
      initialValue={typeof value === 'string' ? value : customRecordCellText(value).replace('—', '')}
      inputType="text"
      onCommit={(raw) => onCommit(raw)}
    />
  )
}

function MentionChips({
  record,
  selectedMention,
  onSelectMention,
  mentionsClickable,
  editing,
  onRemoveMention,
  mentionTargetActive,
  onToggleMentionTarget,
}: {
  record: CustomRecordRow
  selectedMention: SelectedMention | null
  onSelectMention: (recordKey: string, mentionIndex: number) => void
  mentionsClickable: boolean
  editing: boolean
  onRemoveMention: (mentionIndex: number) => void
  mentionTargetActive: boolean
  onToggleMentionTarget: () => void
}) {
  const lastModelMention = record.source === 'model' && record.mentions.length <= 1
  return (
    <div className="flex flex-wrap items-center gap-1">
      {record.mentions.length === 0 && !editing ? (
        <span className="text-xs text-muted-foreground">—</span>
      ) : null}
      {record.mentions.map((mention, mentionIndex) => {
        const selected =
          selectedMention?.recordKey === record.key &&
          selectedMention?.mentionIndex === mentionIndex
        return (
          <span
            key={`${record.key}-m-${mentionIndex}`}
            className={cn(
              'inline-flex max-w-[16rem] items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition-colors',
              selected
                ? 'border-amber-400 bg-amber-200/90 text-foreground dark:bg-amber-500/40'
                : 'border-border bg-muted/60 text-muted-foreground',
            )}
          >
            <button
              type="button"
              disabled={!mentionsClickable}
              onClick={() => onSelectMention(record.key, mentionIndex)}
              title={mentionsClickable ? 'Show this passage in the story' : undefined}
              className={cn(
                'truncate text-left',
                mentionsClickable && 'cursor-pointer hover:text-foreground',
              )}
            >
              {mention.text}
            </button>
            {editing ? (
              <button
                type="button"
                aria-label={`Remove mention ${mention.text}`}
                disabled={lastModelMention}
                title={
                  lastModelMention
                    ? 'Records found by the flow need at least one supporting passage'
                    : 'Remove this mention'
                }
                onClick={() => onRemoveMention(mentionIndex)}
                className={cn(
                  'shrink-0',
                  lastModelMention
                    ? 'cursor-not-allowed opacity-40'
                    : 'cursor-pointer text-muted-foreground hover:text-foreground',
                )}
              >
                <X className="h-3 w-3" />
              </button>
            ) : null}
          </span>
        )
      })}
      {editing ? (
        <Button
          type="button"
          variant={mentionTargetActive ? 'secondary' : 'ghost'}
          size="sm"
          className="h-6 px-2 text-xs"
          onClick={onToggleMentionTarget}
        >
          <Plus className="mr-1 h-3 w-3" />
          {mentionTargetActive ? 'Select passage in story…' : 'Add mention'}
        </Button>
      ) : null}
    </div>
  )
}

function CustomRecordTable({
  table,
  selectedMention,
  onSelectMention,
  mentionsClickable,
  editing,
  mentionTarget,
  onToggleMentionTarget,
  onCommitField,
  onRemoveMention,
  onDeleteRecord,
  onAddRecord,
}: {
  table: CustomRecordTableModel
  selectedMention: SelectedMention | null
  onSelectMention: (recordKey: string, mentionIndex: number) => void
  mentionsClickable: boolean
  editing: boolean
  mentionTarget: MentionTarget | null
  onToggleMentionTarget: (record: CustomRecordRow) => void
  onCommitField: (record: CustomRecordRow, columnName: string, value: unknown) => void
  onRemoveMention: (record: CustomRecordRow, mentionIndex: number) => void
  onDeleteRecord: (record: CustomRecordRow) => void
  onAddRecord: () => void
}) {
  const showConfidence = table.records.some((record) => record.confidence !== null)
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{table.label}</h3>
        {editing ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={onAddRecord}
          >
            <Plus className="mr-1 h-3 w-3" />
            Add record
          </Button>
        ) : null}
      </div>
      {table.records.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">
          No records were found in this story.
        </p>
      ) : (
        <div className="mt-2 overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted text-left text-xs">
                {table.columns.map((column) => (
                  <th key={column.name} className="px-3 py-2 font-medium">
                    {column.label}
                  </th>
                ))}
                <th className="px-3 py-2 font-medium">Mentions</th>
                {showConfidence ? <th className="px-3 py-2 font-medium">Confidence</th> : null}
                {editing ? <th className="w-10 px-2 py-2" /> : null}
              </tr>
            </thead>
            <tbody>
              {table.records.map((record: CustomRecordRow) => (
                <tr key={record.key} className="border-t align-top">
                  {table.columns.map((column) => (
                    <td key={`${record.key}-${column.name}`} className="px-3 py-2">
                      {editing ? (
                        <FieldEditor
                          column={column}
                          value={record.fields[column.name]}
                          onCommit={(value) => onCommitField(record, column.name, value)}
                        />
                      ) : (
                        <FieldCell value={record.fields[column.name]} />
                      )}
                    </td>
                  ))}
                  <td className="px-3 py-2">
                    <MentionChips
                      record={record}
                      selectedMention={selectedMention}
                      onSelectMention={onSelectMention}
                      mentionsClickable={mentionsClickable}
                      editing={editing}
                      onRemoveMention={(mentionIndex) => onRemoveMention(record, mentionIndex)}
                      mentionTargetActive={
                        mentionTarget?.recordType === table.recordType &&
                        mentionTarget?.recordKey === record.key
                      }
                      onToggleMentionTarget={() => onToggleMentionTarget(record)}
                    />
                    {record.source === 'review' ? (
                      <p className="mt-1 text-[11px] text-muted-foreground">Added in review</p>
                    ) : null}
                  </td>
                  {showConfidence ? (
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {confidenceLabel(record.confidence)}
                    </td>
                  ) : null}
                  {editing ? (
                    <td className="px-2 py-2">
                      <button
                        type="button"
                        aria-label="Delete this record"
                        title="Delete this record"
                        className="cursor-pointer text-muted-foreground hover:text-destructive"
                        onClick={() => onDeleteRecord(record)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {table.droppedUngrounded > 0 ? (
        <p className="mt-1 text-xs text-muted-foreground">
          {table.droppedUngrounded} suggested record
          {table.droppedUngrounded === 1 ? ' was' : 's were'} left out because no supporting
          passage was found in the story.
        </p>
      ) : null}
    </div>
  )
}

/**
 * Custom review tab: one table per record type with in-story mention highlighting,
 * plus an edit mode for field values, record add/delete, and mention attach/remove.
 */
export function ProcessedItemCustomRecordsSection({
  runId,
  item,
  onItemUpdated,
  onVerificationDirtyChange,
  reviewLocked = false,
}: ProcessedItemCustomRecordsSectionProps) {
  const { showError, showMessage } = useAppMessage()
  const [selectedMention, setSelectedMention] = useState<SelectedMention | null>(null)
  const [baselineOverlay, setBaselineOverlay] = useState<Record<string, unknown>>(() =>
    cloneOverlay(item.overlay),
  )
  const [draftOverlay, setDraftOverlay] = useState<Record<string, unknown>>(() =>
    cloneOverlay(item.overlay),
  )
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [mentionTarget, setMentionTarget] = useState<MentionTarget | null>(null)
  const [articleTextSelection, setArticleTextSelection] = useState<ArticleTextSelection | null>(
    null,
  )
  const lastItemSyncKeyRef = useRef('')

  const dirty = useMemo(
    () => !overlaysStructurallyEqual(baselineOverlay, draftOverlay),
    [baselineOverlay, draftOverlay],
  )

  const syncKey = `${runId}:${item.id}:${item.overlay_version}`
  useEffect(() => {
    if (lastItemSyncKeyRef.current !== syncKey) {
      lastItemSyncKeyRef.current = syncKey
      const n = cloneOverlay(item.overlay)
      setBaselineOverlay(n)
      setDraftOverlay(n)
      return
    }
    if (!dirty) {
      const n = cloneOverlay(item.overlay)
      setBaselineOverlay(n)
      setDraftOverlay(n)
    }
  }, [item.overlay, syncKey, dirty])

  useEffect(() => {
    onVerificationDirtyChange?.(dirty)
  }, [dirty, onVerificationDirtyChange])

  useEffect(() => {
    if (reviewLocked) {
      setEditing(false)
      setMentionTarget(null)
      setArticleTextSelection(null)
    }
  }, [reviewLocked])

  const baseTables = useMemo(() => buildCustomRecordTables(item.output ?? null), [item.output])
  const tables = useMemo(
    () => applyCustomRecordsOverlayToTables(baseTables, draftOverlay),
    [baseTables, draftOverlay],
  )

  const articleBody =
    typeof item.article_context?.body === 'string' ? item.article_context.body : ''
  const hasArticleBody = articleBody.trim().length > 0

  const ambientHighlights = useMemo(
    () => customAmbientHighlightRanges(articleBody, tables),
    [articleBody, tables],
  )

  const selectedHighlights = useMemo(() => {
    if (!selectedMention) return []
    for (const table of tables) {
      const record = table.records.find((r) => r.key === selectedMention.recordKey)
      const mention = record?.mentions[selectedMention.mentionIndex]
      if (mention) {
        return customMentionHighlightRanges(articleBody, mention.text)
      }
    }
    return []
  }, [selectedMention, tables, articleBody])

  const handleSelectMention = (recordKey: string, mentionIndex: number) => {
    setSelectedMention((current) =>
      current?.recordKey === recordKey && current?.mentionIndex === mentionIndex
        ? null
        : { recordKey, mentionIndex },
    )
  }

  const findRecord = useCallback(
    (recordType: string, recordKey: string): CustomRecordRow | null => {
      const table = tables.find((t) => t.recordType === recordType)
      return table?.records.find((r) => r.key === recordKey) ?? null
    },
    [tables],
  )

  const commitMentions = useCallback(
    (recordType: string, record: CustomRecordRow, mentions: CustomRecordMentionDisplay[]) => {
      setDraftOverlay((draft) =>
        record.source === 'review'
          ? patchUserAddedCustomRecord(draft, recordType, record.key, { mentions })
          : applyCustomRecordMentionsPatch(draft, recordType, record.key, mentions),
      )
    },
    [],
  )

  const handleCommitField = useCallback(
    (recordType: string, record: CustomRecordRow, columnName: string, value: unknown) => {
      if (record.fields[columnName] === value) return
      setDraftOverlay((draft) =>
        record.source === 'review'
          ? patchUserAddedCustomRecord(draft, recordType, record.key, {
              fields: { [columnName]: value },
            })
          : applyCustomRecordFieldsPatch(draft, recordType, record.key, { [columnName]: value }),
      )
    },
    [],
  )

  const handleRemoveMention = useCallback(
    (recordType: string, record: CustomRecordRow, mentionIndex: number) => {
      if (record.source === 'model' && record.mentions.length <= 1) return
      const mentions = record.mentions.filter((_, index) => index !== mentionIndex)
      commitMentions(recordType, record, mentions)
      setSelectedMention(null)
    },
    [commitMentions],
  )

  const handleDeleteRecord = useCallback((recordType: string, record: CustomRecordRow) => {
    setDraftOverlay((draft) =>
      buildRemoveCustomRecordPatch(draft, recordType, record.key, record.source),
    )
    setSelectedMention(null)
    setMentionTarget((current) => (current?.recordKey === record.key ? null : current))
  }, [])

  const handleAddRecord = useCallback((table: CustomRecordTableModel) => {
    setDraftOverlay((draft) =>
      appendUserAddedCustomRecord(draft, table.recordType, {
        key: newUserAddedRecordKey(),
        fields: blankFieldsForColumns(table.columns),
      }),
    )
  }, [])

  const handleToggleMentionTarget = useCallback((recordType: string, record: CustomRecordRow) => {
    setArticleTextSelection(null)
    setMentionTarget((current) =>
      current?.recordType === recordType && current?.recordKey === record.key
        ? null
        : { recordType, recordKey: record.key },
    )
  }, [])

  const handleAddMentionFromSelection = useCallback(
    (selection: ArticleTextSelection, kind: 'mention' | 'quote') => {
      if (!mentionTarget) return
      const record = findRecord(mentionTarget.recordType, mentionTarget.recordKey)
      const text = selection.text.trim()
      if (!record || !text) return
      commitMentions(mentionTarget.recordType, record, [
        ...record.mentions,
        { text, quote: kind === 'quote' },
      ])
      setMentionTarget(null)
      setArticleTextSelection(null)
    },
    [mentionTarget, findRecord, commitMentions],
  )

  const handleDiscard = useCallback(() => {
    setDraftOverlay(JSON.parse(JSON.stringify(baselineOverlay)) as Record<string, unknown>)
    setMentionTarget(null)
    setArticleTextSelection(null)
  }, [baselineOverlay])

  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      const updated = await patchProcessedItemOverlay(
        runId,
        item.id,
        draftOverlay,
        item.overlay_version ?? 0,
      )
      onItemUpdated?.(updated)
      setBaselineOverlay(cloneOverlay(updated.overlay))
      setDraftOverlay(cloneOverlay(updated.overlay))
      setMentionTarget(null)
      setArticleTextSelection(null)
      showMessage('Custom record review saved.')
    } catch (error) {
      if (isApiConflictError(error)) {
        showError(
          'Someone else updated this review while you were editing. Reload the page to pick up the latest version, then make your changes again.',
        )
      } else {
        showError(error instanceof Error ? error.message : 'Could not save the review.')
      }
    } finally {
      setSaving(false)
    }
  }, [runId, item.id, item.overlay_version, draftOverlay, onItemUpdated, showError, showMessage])

  if (tables.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          No custom records were extracted for this story yet. Run a flow with a Custom Extract
          step to pull records you define from each story.
        </CardContent>
      </Card>
    )
  }

  const mentionTargetArmed = editing && mentionTarget !== null

  const tablesPane = (
    <div className="min-h-0 space-y-6 overflow-y-auto">
      {tables.map((table) => (
        <CustomRecordTable
          key={table.recordType}
          table={table}
          selectedMention={selectedMention}
          onSelectMention={handleSelectMention}
          mentionsClickable={hasArticleBody}
          editing={editing}
          mentionTarget={mentionTarget}
          onToggleMentionTarget={(record) => handleToggleMentionTarget(table.recordType, record)}
          onCommitField={(record, columnName, value) =>
            handleCommitField(table.recordType, record, columnName, value)
          }
          onRemoveMention={(record, mentionIndex) =>
            handleRemoveMention(table.recordType, record, mentionIndex)
          }
          onDeleteRecord={(record) => handleDeleteRecord(table.recordType, record)}
          onAddRecord={() => handleAddRecord(table)}
        />
      ))}
    </div>
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Review custom records</h2>
          <p className="text-sm text-muted-foreground">
            {editing
              ? mentionTargetArmed
                ? 'Select a passage in the story to attach it as a mention.'
                : 'Edit values directly in the table. Changes are kept as a draft until you save.'
              : 'Records your flow pulled from this story. Select a mention to see the supporting passage in the story.'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {dirty ? (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={saving}
                onClick={handleDiscard}
              >
                Discard changes
              </Button>
              <Button type="button" size="sm" disabled={saving} onClick={() => void handleSave()}>
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                {saving ? 'Saving…' : 'Save review'}
              </Button>
            </>
          ) : null}
          <Button
            type="button"
            variant={editing ? 'secondary' : 'outline'}
            size="sm"
            disabled={reviewLocked || saving}
            onClick={() => {
              setEditing((current) => !current)
              setMentionTarget(null)
              setArticleTextSelection(null)
            }}
          >
            <Pencil className="mr-2 h-4 w-4" />
            {editing ? 'Done editing' : 'Edit records'}
          </Button>
        </div>
      </div>

      {hasArticleBody ? (
        <div className="grid min-h-0 gap-4 lg:grid-cols-2 lg:items-stretch h-[min(44rem,calc(100dvh-12rem))]">
          <div className="min-h-0 overflow-y-auto rounded-md border border-border bg-muted/30 p-2.5 text-sm">
            <ProcessedItemArticleBody
              body={articleBody}
              ambientHighlights={ambientHighlights}
              highlights={selectedHighlights}
              scrollWhenKey={
                selectedMention
                  ? `${selectedMention.recordKey}:${selectedMention.mentionIndex}`
                  : null
              }
              interactionMode={mentionTargetArmed ? 'select-passage' : 'locked'}
              onTextSelectionChange={mentionTargetArmed ? setArticleTextSelection : undefined}
              activeTextSelection={mentionTargetArmed ? articleTextSelection : null}
              onAddOccurrenceFromSelection={
                mentionTargetArmed ? handleAddMentionFromSelection : undefined
              }
            />
            {selectedMention && selectedHighlights.length === 0 ? (
              <p className="mt-2 border-t border-border/60 pt-2 text-xs text-muted-foreground">
                No matching passage was found in this story for this mention.
              </p>
            ) : null}
          </div>
          {tablesPane}
        </div>
      ) : (
        tablesPane
      )}
    </div>
  )
}
