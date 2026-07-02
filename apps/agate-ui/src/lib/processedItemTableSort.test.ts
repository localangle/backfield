import { describe, expect, it } from 'vitest'

import type { ProcessedItemSummary } from '@/lib/api'
import { sortProcessedItems } from '@/lib/processedItemTableSort'

function item(
  overrides: Partial<ProcessedItemSummary> & Pick<ProcessedItemSummary, 'id'>,
): ProcessedItemSummary {
  return {
    run_id: 'run-1',
    source_file: null,
    status: 'pending',
    error: null,
    created_at: '2026-07-01T12:00:00Z',
    updated_at: '2026-07-01T12:00:00Z',
    ...overrides,
  }
}

describe('sortProcessedItems', () => {
  it('sorts by id ascending by default tie-breaker', () => {
    const rows = [item({ id: 3 }), item({ id: 1 }), item({ id: 2 })]
    expect(sortProcessedItems(rows, 'id', 'asc').map((row) => row.id)).toEqual([1, 2, 3])
  })

  it('sorts by status using workflow order', () => {
    const rows = [
      item({ id: 1, status: 'failed' }),
      item({ id: 2, status: 'pending' }),
      item({ id: 3, status: 'succeeded' }),
    ]
    expect(sortProcessedItems(rows, 'status', 'asc').map((row) => row.id)).toEqual([2, 3, 1])
  })

  it('sorts by source label case-insensitively', () => {
    const rows = [
      item({ id: 1, source_file: 's3://bucket/zulu.json' }),
      item({ id: 2, source_file: 's3://bucket/alpha.json' }),
      item({ id: 3, input_preview: 'Beta headline' }),
    ]
    expect(sortProcessedItems(rows, 'source', 'asc').map((row) => row.id)).toEqual([2, 3, 1])
  })

  it('puts missing duration values last', () => {
    const rows = [
      item({ id: 1, duration_ms: 5000 }),
      item({ id: 2, duration_ms: null }),
      item({ id: 3, duration_ms: 1000 }),
    ]
    expect(sortProcessedItems(rows, 'duration', 'asc').map((row) => row.id)).toEqual([3, 1, 2])
  })
})
