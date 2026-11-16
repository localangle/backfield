import { describe, expect, it } from 'vitest'
import {
  createRunFailureCopy,
  runEmptyItemsCopy,
  s3BatchAlreadyProcessedCount,
} from '@/lib/runEmptyItemsCopy'

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

describe('createRunFailureCopy', () => {
  it('explains empty S3 folders without technical wording', () => {
    const copy = createRunFailureCopy(
      new Error('API error: 400 - {"detail":"No JSON objects found under s3://bucket/prefix/"}'),
    )
    expect(copy.title).toBe('Nothing to run')
    expect(copy.description).toContain('no JSON files')
  })
})
