import type { ProcessedItemSummary } from '@/lib/api'
import { processedItemSourceLabel } from '@/lib/review/content/sourceDisplay'

export type ProcessedItemSortColumn =
  | 'id'
  | 'source'
  | 'status'
  | 'duration'
  | 'estimated_cost'
  | 'created_at'

export type ProcessedItemSortDirection = 'asc' | 'desc'

const STATUS_SORT_ORDER: Record<ProcessedItemSummary['status'], number> = {
  pending: 0,
  running: 1,
  succeeded: 2,
  failed: 3,
  timed_out: 4,
  skipped: 5,
}

export function processedItemSourceSortKey(
  item: Pick<ProcessedItemSummary, 'source_file' | 'input_preview' | 'input_headline'>,
): string {
  return (
    processedItemSourceLabel(item)?.toLowerCase() ??
    item.input_headline?.trim().toLowerCase() ??
    item.source_file?.toLowerCase() ??
    ''
  )
}

function compareStrings(a: string, b: string, direction: ProcessedItemSortDirection): number {
  const cmp = a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })
  return direction === 'asc' ? cmp : -cmp
}

function compareNullableNumbers(
  a: number | null | undefined,
  b: number | null | undefined,
  direction: ProcessedItemSortDirection,
): number {
  const aMissing = a == null
  const bMissing = b == null
  if (aMissing && bMissing) return 0
  if (aMissing) return 1
  if (bMissing) return -1
  const cmp = a - b
  return direction === 'asc' ? cmp : -cmp
}

function compareProcessedItems(
  left: ProcessedItemSummary,
  right: ProcessedItemSummary,
  column: ProcessedItemSortColumn,
  direction: ProcessedItemSortDirection,
): number {
  switch (column) {
    case 'id':
      return compareNullableNumbers(left.id, right.id, direction)
    case 'source':
      return compareStrings(
        processedItemSourceSortKey(left),
        processedItemSourceSortKey(right),
        direction,
      )
    case 'status':
      return compareNullableNumbers(
        STATUS_SORT_ORDER[left.status],
        STATUS_SORT_ORDER[right.status],
        direction,
      )
    case 'duration':
      return compareNullableNumbers(left.duration_ms, right.duration_ms, direction)
    case 'estimated_cost':
      return compareNullableNumbers(left.estimated_ai_cost, right.estimated_ai_cost, direction)
    case 'created_at':
      return compareStrings(left.created_at, right.created_at, direction)
    default:
      return 0
  }
}

export function sortProcessedItems(
  items: ProcessedItemSummary[],
  column: ProcessedItemSortColumn,
  direction: ProcessedItemSortDirection,
): ProcessedItemSummary[] {
  return [...items].sort((left, right) => {
    const primary = compareProcessedItems(left, right, column, direction)
    if (primary !== 0) return primary
    return left.id - right.id
  })
}
