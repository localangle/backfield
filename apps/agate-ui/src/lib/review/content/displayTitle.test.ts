import { describe, expect, it } from 'vitest'
import { processedItemDisplayTitle } from './displayTitle'

describe('processedItemDisplayTitle', () => {
  it('prefers input headline over article_context', () => {
    expect(
      processedItemDisplayTitle({
        id: 58,
        article_context: { headline: 'White Sox beat Cubs', body: '', resolution: 'substrate' },
        input: { headline: 'From input' },
      }),
    ).toBe('From input')
  })

  it('uses article_context headline when input has none', () => {
    expect(
      processedItemDisplayTitle({
        id: 58,
        article_context: { headline: 'White Sox beat Cubs', body: '', resolution: 'substrate' },
        input: {},
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

  it('ignores generic Article substrate headline in favor of input', () => {
    expect(
      processedItemDisplayTitle({
        id: 3,
        article_context: { headline: 'Article', body: '', resolution: 'substrate' },
        input: { headline: 'Real story headline' },
      }),
    ).toBe('Real story headline')
  })
})
