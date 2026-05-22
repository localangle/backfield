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

  it('falls back to model mentions when system occurrences belong to another row', () => {
    const occs = readMentionOccurrencesFromRow({
      location: {
        original_text: 'Buying a new suit at Carsons for an interview.',
        mentions: [{ text: 'Buying a new suit at Carsons for an interview.' }],
      },
      mention_occurrences: [
        {
          mention_text: '"Buying polos at Kohl\'s. Sexy sexy." — Andy Green',
          occurrence_order: 0,
          source_kind: 'system_extraction',
        },
      ],
    })
    expect(occs).toHaveLength(1)
    expect(occs[0]?.mentionText).toBe('Buying a new suit at Carsons for an interview.')
  })

  it('keeps user-reviewed occurrences even when they differ from model text', () => {
    const occs = readMentionOccurrencesFromRow({
      location: {
        original_text: 'Model text',
        mentions: [{ text: 'Model text' }],
      },
      mention_occurrences: [
        {
          mention_text: 'Reviewed text',
          occurrence_order: 0,
          source_kind: 'user_review',
        },
      ],
    })
    expect(occs[0]?.mentionText).toBe('Reviewed text')
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
