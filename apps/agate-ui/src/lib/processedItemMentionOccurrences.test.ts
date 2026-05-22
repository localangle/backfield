import { describe, expect, it } from 'vitest'
import {
  buildOccurrencesOverlayPayload,
  readMentionOccurrencesFromRow,
  recomputeOccurrenceSpans,
} from './processedItemMentionOccurrences'

describe('readMentionOccurrencesFromRow', () => {
  it('reads mention_occurrences from merged row', () => {
    const occs = readMentionOccurrencesFromRow({
      mention_occurrences: [
        { mention_text: 'Ohio in lede.', occurrence_order: 0 },
        { mention_text: 'Back in Ohio.', occurrence_order: 1 },
      ],
    })
    expect(occs).toHaveLength(2)
    expect(occs[0]?.mentionText).toBe('Ohio in lede.')
  })
})

describe('recomputeOccurrenceSpans', () => {
  it('finds second identical mention after first', () => {
    const body = 'Ohio first. Then Ohio again.'
    const out = recomputeOccurrenceSpans(body, [
      {
        clientId: 'a',
        mentionText: 'Ohio',
        startChar: null,
        endChar: null,
        occurrenceOrder: 0,
        suppressed: false,
      },
      {
        clientId: 'b',
        mentionText: 'Ohio',
        startChar: null,
        endChar: null,
        occurrenceOrder: 1,
        suppressed: false,
      },
    ])
    expect(out[0]?.startChar).toBe(0)
    expect(out[1]?.startChar).toBe(17)
  })
})

describe('buildOccurrencesOverlayPayload', () => {
  it('serializes client_id and mention_text', () => {
    const payload = buildOccurrencesOverlayPayload([
      {
        clientId: 'uuid-1',
        mentionText: 'Hello',
        startChar: 0,
        endChar: 5,
        occurrenceOrder: 0,
        suppressed: false,
      },
    ])
    expect(payload[0]).toMatchObject({ client_id: 'uuid-1', mention_text: 'Hello' })
  })
})
