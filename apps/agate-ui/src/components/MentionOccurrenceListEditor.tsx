import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { MentionOccurrenceDraft } from '@/lib/processedItemMentionOccurrences'
import { createEmptyMentionOccurrence } from '@/lib/processedItemMentionOccurrences'
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'

export type MentionOccurrenceListEditorProps = {
  occurrences: MentionOccurrenceDraft[]
  onChange: (occurrences: MentionOccurrenceDraft[]) => void
  disabled?: boolean
  selectedClientId?: string | null
  onSelectOccurrence?: (clientId: string) => void
}

export function MentionOccurrenceListEditor({
  occurrences,
  onChange,
  disabled = false,
  selectedClientId = null,
  onSelectOccurrence,
}: MentionOccurrenceListEditorProps) {
  const visible = occurrences.filter((o) => !o.suppressed)

  const updateAt = (clientId: string, patch: Partial<MentionOccurrenceDraft>) => {
    onChange(
      occurrences.map((o) => (o.clientId === clientId ? { ...o, ...patch } : o)),
    )
  }

  const move = (clientId: string, direction: -1 | 1) => {
    const idx = visible.findIndex((o) => o.clientId === clientId)
    if (idx < 0) return
    const nextIdx = idx + direction
    if (nextIdx < 0 || nextIdx >= visible.length) return
    const reordered = [...visible]
    const tmp = reordered[idx]!
    reordered[idx] = reordered[nextIdx]!
    reordered[nextIdx] = tmp
    const orderMap = new Map(reordered.map((o, i) => [o.clientId, i]))
    onChange(
      occurrences.map((o) =>
        orderMap.has(o.clientId) ? { ...o, occurrenceOrder: orderMap.get(o.clientId)! } : o,
      ),
    )
  }

  const remove = (clientId: string) => {
    onChange(
      occurrences.map((o) =>
        o.clientId === clientId ? { ...o, suppressed: true } : o,
      ),
    )
  }

  const add = () => {
    const maxOrder = occurrences.reduce((m, o) => Math.max(m, o.occurrenceOrder), -1)
    onChange([...occurrences, createEmptyMentionOccurrence(maxOrder + 1)])
  }

  return (
    <div className="space-y-2 sm:col-span-2">
      <div className="flex items-center justify-between gap-2">
        <Label>Mentions in story</Label>
        <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={add}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          Add mention
        </Button>
      </div>
      {visible.length === 0 ? (
        <p className="text-sm text-muted-foreground">No mentions yet. Add one from the story.</p>
      ) : (
        <ul className="space-y-2">
          {visible
            .sort((a, b) => a.occurrenceOrder - b.occurrenceOrder)
            .map((occ, index) => {
              const selected = selectedClientId === occ.clientId
              return (
                <li
                  key={occ.clientId}
                  className={
                    selected
                      ? 'rounded-md border border-primary/50 bg-muted/40 p-2'
                      : 'rounded-md border border-border p-2'
                  }
                >
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <button
                      type="button"
                      className="text-xs font-medium text-muted-foreground hover:text-foreground"
                      disabled={disabled}
                      onClick={() => onSelectOccurrence?.(occ.clientId)}
                    >
                      Mention {index + 1}
                    </button>
                    <div className="flex shrink-0 gap-0.5">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        disabled={disabled || index === 0}
                        aria-label="Move up"
                        onClick={() => move(occ.clientId, -1)}
                      >
                        <ArrowUp className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        disabled={disabled || index === visible.length - 1}
                        aria-label="Move down"
                        onClick={() => move(occ.clientId, 1)}
                      >
                        <ArrowDown className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-destructive"
                        disabled={disabled}
                        aria-label="Remove mention"
                        onClick={() => remove(occ.clientId)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                  <Textarea
                    value={occ.mentionText}
                    disabled={disabled}
                    rows={2}
                    className="min-h-0 resize-y text-sm"
                    placeholder="Text as it appears in the story"
                    onChange={(e) => updateAt(occ.clientId, { mentionText: e.target.value })}
                    onFocus={() => onSelectOccurrence?.(occ.clientId)}
                  />
                </li>
              )
            })}
        </ul>
      )}
    </div>
  )
}
