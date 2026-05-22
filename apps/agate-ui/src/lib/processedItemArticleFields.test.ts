import { describe, expect, it } from 'vitest'
import { readArticleFieldsFromProcessedItem, applyArticleFieldsToOverlay } from './processedItemArticleFields'
import type { ProcessedItem } from '@/lib/api'

describe('processedItemArticleFields', () => {
  it('prefers overlay article fields over input and output', () => {
    const item = {
      id: 1,
      run_id: 'r1',
      input: { publication: 'Input Pub', headline: 'Input title' },
      output: { publication: 'Output Pub', author: 'Jane' },
      overlay: { article: { publication: 'Overlay Pub', headline: 'Overlay head' } },
    } as ProcessedItem
    const fields = readArticleFieldsFromProcessedItem(item)
    expect(fields.publication).toBe('Overlay Pub')
    expect(fields.headline).toBe('Overlay head')
    expect(fields.author).toBe('Jane')
  })

  it('reads article fields from json_output consolidated and stylebook_output', () => {
    const item = {
      id: 1,
      run_id: 'r1',
      input: {},
      output: {
        json_output: {
          consolidated: { headline: 'JSON headline', publication: 'JSON pub' },
        },
        stylebook_output: {
          headline: 'Stylebook headline',
          author: 'Sam',
          places: { areas: {}, points: [] },
          success: true,
        },
      },
    } as ProcessedItem
    const fields = readArticleFieldsFromProcessedItem(item)
    expect(fields.headline).toBe('JSON headline')
    expect(fields.publication).toBe('JSON pub')
    expect(fields.author).toBe('Sam')
  })

  it('writes article fields into overlay', () => {
    const next = applyArticleFieldsToOverlay(
      { locations: { by_anchor: {}, user_added: [], removed_anchors: [] } },
      {
        publication: 'Trib',
        url: 'https://example.com',
        headline: 'Story',
        author: 'A',
        pub_date: '2026-05-21',
      },
    )
    expect((next.article as Record<string, string>).publication).toBe('Trib')
    expect(next.locations).toBeDefined()
  })
})
