import { describe, expect, it } from 'vitest'
import { processedItemDisplayTitle } from './processedItemDisplayTitle'

describe('processedItemDisplayTitle', () => {
  it('prefers article_context headline', () => {
    expect(
      processedItemDisplayTitle({
        id: 58,
        article_context: { headline: 'White Sox beat Cubs', body: '', resolution: 'substrate' },
        input: { headline: 'From input' },
      }),
    ).toBe('White Sox beat Cubs')
  })

  it('falls back to input then output headline keys', () => {
    expect(
      processedItemDisplayTitle({
        id: 1,
        input: { title: '  Story title  ' },
      }),
    ).toBe('Story title')
    expect(
      processedItemDisplayTitle({
        id: 2,
        input: {},
        output: { input_headline: 'Output headline' },
      }),
    ).toBe('Output headline')
  })

  it('uses processed item id when no headline is available', () => {
    expect(processedItemDisplayTitle({ id: 58, input: {} })).toBe('Processed Item #58')
  })
})
