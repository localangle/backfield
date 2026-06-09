import { describe, expect, it } from 'vitest'
import {
  formatSemanticIndexingDetail,
  normalizeProcessedItemSemanticIndexing,
  semanticIndexingStatusLabel,
  shouldShowSemanticIndexingSummary,
} from './semanticIndexingDisplay'

describe('semanticIndexingDisplay', () => {
  it('normalizes missing semantic indexing as not enabled', () => {
    expect(normalizeProcessedItemSemanticIndexing(undefined).status).toBe('not_enabled')
  })

  it('formats succeeded detail with indexed count', () => {
    const summary = normalizeProcessedItemSemanticIndexing({
      status: 'succeeded',
      enabled: true,
      document_count: 3,
      indexed_count: 3,
      pending_count: 0,
      failed_count: 0,
    })
    expect(semanticIndexingStatusLabel(summary.status)).toBe('Complete')
    expect(formatSemanticIndexingDetail(summary)).toBe('3 documents indexed')
    expect(shouldShowSemanticIndexingSummary(summary)).toBe(true)
  })

  it('formats partial detail with failed count', () => {
    const summary = normalizeProcessedItemSemanticIndexing({
      status: 'partial',
      enabled: true,
      document_count: 4,
      indexed_count: 2,
      pending_count: 1,
      failed_count: 1,
    })
    expect(semanticIndexingStatusLabel(summary.status)).toBe('Partial')
    expect(formatSemanticIndexingDetail(summary)).toBe('2 documents indexed')
  })

  it('hides not-enabled summary from the card', () => {
    const summary = normalizeProcessedItemSemanticIndexing({
      status: 'not_enabled',
      enabled: false,
      document_count: 0,
      indexed_count: 0,
      pending_count: 0,
      failed_count: 0,
    })
    expect(shouldShowSemanticIndexingSummary(summary)).toBe(false)
    expect(formatSemanticIndexingDetail(summary)).toBeNull()
  })

  it('shows in-progress copy for running items', () => {
    const summary = normalizeProcessedItemSemanticIndexing({
      status: 'running',
      enabled: false,
      document_count: 0,
      indexed_count: 0,
      pending_count: 0,
      failed_count: 0,
    })
    expect(formatSemanticIndexingDetail(summary)).toBe(
      'Semantic search is in progress for this item.',
    )
  })
})
