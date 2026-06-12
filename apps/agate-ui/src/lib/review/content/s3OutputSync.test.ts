import { describe, expect, it } from 'vitest'

import { s3OutputUploadsFromItemOutput } from '@/lib/review/content/s3OutputSync'

describe('s3OutputUploadsFromItemOutput', () => {
  it('returns empty for missing or non-object output', () => {
    expect(s3OutputUploadsFromItemOutput(null)).toEqual([])
    expect(s3OutputUploadsFromItemOutput(undefined)).toEqual([])
    expect(s3OutputUploadsFromItemOutput({})).toEqual([])
  })

  it('finds payloads with bucket, key, and consolidated body', () => {
    const output = {
      json_output: { consolidated: { text: 'Hi' } },
      s3_output: {
        consolidated: { text: 'Hi' },
        s3_bucket: 'out-bucket',
        s3_key: 'out/2026-06-01/story-output.json',
      },
      place_extract: { locations: [] },
    }
    expect(s3OutputUploadsFromItemOutput(output)).toEqual([
      {
        bucket: 'out-bucket',
        key: 'out/2026-06-01/story-output.json',
        syncedAt: null,
        syncError: null,
      },
    ])
  })

  it('ignores payloads without a consolidated body', () => {
    const output = {
      s3_output: { s3_bucket: 'b', s3_key: 'k' },
    }
    expect(s3OutputUploadsFromItemOutput(output)).toEqual([])
  })

  it('carries sync state when stamped by the worker', () => {
    const output = {
      s3_output: {
        consolidated: {},
        s3_bucket: 'b',
        s3_key: 'k',
        s3_synced_at: '2026-06-12T10:00:00+00:00',
        s3_sync_error: 'access denied',
      },
    }
    expect(s3OutputUploadsFromItemOutput(output)).toEqual([
      {
        bucket: 'b',
        key: 'k',
        syncedAt: '2026-06-12T10:00:00+00:00',
        syncError: 'access denied',
      },
    ])
  })
})
