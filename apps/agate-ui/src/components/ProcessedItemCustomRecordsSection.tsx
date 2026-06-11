import { useMemo, useState } from 'react'
import { ProcessedItemArticleBody } from '@/components/ProcessedItemArticleBody'
import { Card, CardContent } from '@/components/ui/card'
import type { ProcessedItem } from '@/lib/api'
import {
  buildCustomRecordTables,
  customAmbientHighlightRanges,
  customMentionHighlightRanges,
  customRecordCellListItems,
  customRecordCellText,
  type CustomRecordRow,
  type CustomRecordTableModel,
} from '@/lib/review/content/customRecordsDisplay'
import { cn } from '@/lib/utils'

export type ProcessedItemCustomRecordsSectionProps = {
  item: ProcessedItem
}

type SelectedMention = {
  recordKey: string
  mentionIndex: number
}

function confidenceLabel(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—'
  return value.toFixed(2)
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

function CustomRecordTable({
  table,
  selectedMention,
  onSelectMention,
  mentionsClickable,
}: {
  table: CustomRecordTableModel
  selectedMention: SelectedMention | null
  onSelectMention: (recordKey: string, mentionIndex: number) => void
  mentionsClickable: boolean
}) {
  const showConfidence = table.records.some((record) => record.confidence !== null)
  return (
    <div>
      <h3 className="text-sm font-semibold">{table.label}</h3>
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
              </tr>
            </thead>
            <tbody>
              {table.records.map((record: CustomRecordRow) => (
                <tr key={record.key} className="border-t align-top">
                  {table.columns.map((column) => (
                    <td key={`${record.key}-${column.name}`} className="px-3 py-2">
                      <FieldCell value={record.fields[column.name]} />
                    </td>
                  ))}
                  <td className="px-3 py-2">
                    {record.mentions.length === 0 ? (
                      <span className="text-xs text-muted-foreground">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {record.mentions.map((mention, mentionIndex) => {
                          const selected =
                            selectedMention?.recordKey === record.key &&
                            selectedMention?.mentionIndex === mentionIndex
                          return (
                            <button
                              key={`${record.key}-m-${mentionIndex}`}
                              type="button"
                              disabled={!mentionsClickable}
                              onClick={() => onSelectMention(record.key, mentionIndex)}
                              title={
                                mentionsClickable
                                  ? 'Show this passage in the story'
                                  : undefined
                              }
                              className={cn(
                                'inline-flex max-w-[16rem] items-center truncate rounded-full border px-2 py-0.5 text-left text-xs transition-colors',
                                selected
                                  ? 'border-amber-400 bg-amber-200/90 text-foreground dark:bg-amber-500/40'
                                  : 'border-border bg-muted/60 text-muted-foreground',
                                mentionsClickable &&
                                  !selected &&
                                  'cursor-pointer hover:bg-amber-100/80 hover:text-foreground dark:hover:bg-amber-500/25',
                              )}
                            >
                              {mention.text}
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </td>
                  {showConfidence ? (
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {confidenceLabel(record.confidence)}
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

/** Read-only Custom review tab: one table per record type plus in-story mention highlighting. */
export function ProcessedItemCustomRecordsSection({
  item,
}: ProcessedItemCustomRecordsSectionProps) {
  const [selectedMention, setSelectedMention] = useState<SelectedMention | null>(null)

  const output = useMemo(() => {
    const reviewed = item.reviewed_output
    if (reviewed && typeof reviewed === 'object' && Object.keys(reviewed).length > 0) {
      return reviewed
    }
    return item.output ?? null
  }, [item.reviewed_output, item.output])

  const tables = useMemo(() => buildCustomRecordTables(output), [output])

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

  const tablesPane = (
    <div className="min-h-0 space-y-6 overflow-y-auto">
      {tables.map((table) => (
        <CustomRecordTable
          key={table.recordType}
          table={table}
          selectedMention={selectedMention}
          onSelectMention={handleSelectMention}
          mentionsClickable={hasArticleBody}
        />
      ))}
    </div>
  )

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Review custom records</h2>
        <p className="text-sm text-muted-foreground">
          Records your flow pulled from this story. Select a mention to see the supporting
          passage in the story.
        </p>
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
              interactionMode="locked"
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
