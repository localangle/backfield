import { describe, expect, it } from 'vitest'

import {
  flowChangedSinceRun,
  graphSpecSnapshotJsonFromRunResult,
  parseGraphSpecFromJson,
  resolveRunGraphSpecForDisplay,
  s3InputSourceForRun,
} from './runGraphSpec'

const aprilSpec = JSON.stringify({
  nodes: [
    {
      type: 'S3Input',
      params: { bucket: 'agate-ai', folder_path: 'data/chicago-sun-times/input/2026-04-monthly/' },
    },
  ],
})

const marchSpec = JSON.stringify({
  nodes: [
    {
      type: 'S3Input',
      params: { bucket: 'agate-ai', folder_path: 'data/chicago-sun-times/input/2026-03-monthly/' },
    },
  ],
})

describe('runGraphSpec', () => {
  it('reads graph_spec_json from run result payload', () => {
    expect(
      graphSpecSnapshotJsonFromRunResult({
        graph_spec_json: aprilSpec,
        s3_batch: { valid_executed: 10 },
      }),
    ).toBe(aprilSpec)
  })

  it('prefers pinned snapshot over live graph for S3 source display', () => {
    const live = parseGraphSpecFromJson(marchSpec)
    const { source, usedSnapshot } = s3InputSourceForRun(aprilSpec, live ?? undefined)
    expect(usedSnapshot).toBe(true)
    expect(source?.uri).toBe('s3://agate-ai/data/chicago-sun-times/input/2026-04-monthly/')
  })

  it('falls back to live graph when no snapshot exists', () => {
    const live = parseGraphSpecFromJson(marchSpec)
    const { spec, usedSnapshot } = resolveRunGraphSpecForDisplay(null, live ?? undefined)
    expect(usedSnapshot).toBe(false)
    expect(spec?.nodes?.[0]?.params?.folder_path).toContain('2026-03')
  })

  it('detects flow changes from snapshot vs live spec json', () => {
    expect(flowChangedSinceRun(aprilSpec, marchSpec, undefined)).toBe(true)
    expect(flowChangedSinceRun(aprilSpec, aprilSpec, undefined)).toBe(false)
    expect(flowChangedSinceRun(null, marchSpec, undefined)).toBe(null)
  })

  it('prefers API flow_changed_since_run when provided', () => {
    expect(flowChangedSinceRun(aprilSpec, marchSpec, false)).toBe(false)
  })
})
