import { useEffect, useMemo, useRef, useState } from 'react'
import { Search } from 'lucide-react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import {
  categoryHeading,
  countScaffoldNodeTypes,
  shouldShowChooserSearch,
  type CompatibleNodeEntry,
  type CompatibleNextNodesResult,
} from '@/lib/nodeCompatibility'

type AddNodeChooserProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  compatibility: CompatibleNextNodesResult
  onSelect: (type: string) => void
}

type FlatRow = CompatibleNodeEntry & { rowKey: string }

function groupRows(rows: FlatRow[]): Array<{ category: string; heading: string; rows: FlatRow[] }> {
  const byCategory = new Map<string, FlatRow[]>()
  for (const row of rows) {
    const list = byCategory.get(row.category) ?? []
    list.push(row)
    byCategory.set(row.category, list)
  }
  return [...byCategory.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([category, categoryRows]) => ({
      category,
      heading: categoryHeading(category),
      rows: categoryRows,
    }))
}

export default function AddNodeChooser({
  open,
  onOpenChange,
  compatibility,
  onSelect,
}: AddNodeChooserProps) {
  const [query, setQuery] = useState('')
  const [highlightIndex, setHighlightIndex] = useState(0)
  const listRef = useRef<HTMLDivElement>(null)

  const allRows = useMemo<FlatRow[]>(() => {
    const enabled = compatibility.enabled.map((row) => ({ ...row, rowKey: `e-${row.type}` }))
    const disabled = compatibility.disabled.map((row) => ({ ...row, rowKey: `d-${row.type}` }))
    return [...enabled, ...disabled]
  }, [compatibility])

  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return allRows
    return allRows.filter(
      (row) =>
        row.label.toLowerCase().includes(q) ||
        row.description.toLowerCase().includes(q) ||
        row.type.toLowerCase().includes(q),
    )
  }, [allRows, query])

  const selectableRows = useMemo(
    () => filteredRows.filter((row) => row.enabled),
    [filteredRows],
  )

  const grouped = useMemo(() => groupRows(filteredRows), [filteredRows])
  const showSearch = shouldShowChooserSearch(countScaffoldNodeTypes())

  useEffect(() => {
    if (!open) {
      setQuery('')
      setHighlightIndex(0)
    }
  }, [open])

  useEffect(() => {
    setHighlightIndex(0)
  }, [query])

  const handleSelect = (type: string) => {
    onSelect(type)
    onOpenChange(false)
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      onOpenChange(false)
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const pick = selectableRows[highlightIndex]
      if (pick) handleSelect(pick.type)
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlightIndex((i) => Math.min(i + 1, Math.max(selectableRows.length - 1, 0)))
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlightIndex((i) => Math.max(i - 1, 0))
    }
  }

  let selectableCursor = -1

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-hidden p-0" hideCloseButton={false}>
        <DialogHeader className="space-y-1 border-b px-4 py-4">
          <DialogTitle>Add a step</DialogTitle>
          <DialogDescription>Choose what happens next in your flow.</DialogDescription>
          {showSearch && (
            <div className="relative pt-2">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Search steps…"
                className="pl-9"
                aria-label="Search steps"
              />
            </div>
          )}
        </DialogHeader>

        <div ref={listRef} className="max-h-[50vh] overflow-y-auto px-2 py-2" role="listbox">
          {compatibility.enabled.length === 0 && compatibility.disabled.length === 0 && (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">
              No steps are available to add here yet.
            </p>
          )}

          {compatibility.enabled.length === 0 && compatibility.disabled.length > 0 && (
            <p className="px-3 py-3 text-sm text-muted-foreground">
              Nothing can be added yet. Check the requirements below for what this branch needs
              first.
            </p>
          )}

          {grouped.map((group) => (
            <div key={group.category} className="mb-3">
              <p className="px-3 py-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {group.heading}
              </p>
              <div className="space-y-1">
                {group.rows.map((row) => {
                  const isSelectable = row.enabled
                  if (isSelectable) selectableCursor += 1
                  const isHighlighted = isSelectable && selectableCursor === highlightIndex

                  return (
                    <button
                      key={row.rowKey}
                      type="button"
                      disabled={!row.enabled}
                      onClick={() => row.enabled && handleSelect(row.type)}
                      className={cn(
                        'w-full rounded-md px-3 py-2 text-left transition-colors',
                        row.enabled && 'hover:bg-muted',
                        row.enabled && isHighlighted && 'bg-muted ring-1 ring-primary/30',
                        !row.enabled && 'cursor-not-allowed opacity-60',
                      )}
                    >
                      <span className="block text-sm font-medium">{row.label}</span>
                      {row.description && (
                        <span className="mt-0.5 block text-xs text-muted-foreground">
                          {row.description}
                        </span>
                      )}
                      {!row.enabled && row.reason && (
                        <span className="mt-1 block text-xs text-destructive">{row.reason}</span>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
