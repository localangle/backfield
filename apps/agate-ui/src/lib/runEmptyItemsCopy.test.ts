import { describe, expect, it } from 'vitest'
import { runEmptyItemsCopy, s3BatchAlreadyProcessedCount } from '@/lib/runEmptyItemsCopy'

describe('runEmptyItemsCopy', () => {
  it('explains already-processed S3 scans', () => {
    const copy = runEmptyItemsCopy({
      status: 'completed',
      s3_batch: {
        total_json_objects: 12,
        skipped_invalid: 0,
        skipped_cap: 0,
        skipped_unchanged: 12,
        skipped_claim_conflict: 0,
        valid_executed: 0,
      },
    })
    expect(copy.title).toBe('Nothing new to process')
    expect(copy.description).toContain('12 files')
    expect(copy.description).toContain('Reprocess completed files')
  })

  it('keeps the generic empty message while a run is still active', () => {
    const copy = runEmptyItemsCopy({
      status: 'running',
      s3_batch: {
        total_json_objects: 3,
        skipped_invalid: 0,
        skipped_cap: 0,
        skipped_unchanged: 3,
        skipped_claim_conflict: 0,
        valid_executed: 0,
      },
    })
    expect(copy.title).toBe('No Items Processed')
  })
})

describe('s3BatchAlreadyProcessedCount', () => {
  it('reads skipped_unchanged', () => {
    expect(
      s3BatchAlreadyProcessedCount({
        total_json_objects: 2,
        skipped_invalid: 0,
        skipped_cap: 0,
        skipped_unchanged: 2,
        skipped_claim_conflict: 0,
        valid_executed: 0,
      }),
    ).toBe(2)
    expect(s3BatchAlreadyProcessedCount(null)).toBe(0)
  })
})
