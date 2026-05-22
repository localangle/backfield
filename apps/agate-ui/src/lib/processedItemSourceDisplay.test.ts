import { describe, expect, it } from 'vitest'
import { isBatchFileSource, processedItemSourceLabel } from './processedItemSourceDisplay'

describe('processedItemSourceDisplay', () => {
  it('treats inline labels as non-file sources', () => {
    expect(isBatchFileSource('inline:json')).toBe(false)
    expect(isBatchFileSource('inline:text')).toBe(false)
    expect(isBatchFileSource('folder/article.json')).toBe(true)
  })

  it('prefers input preview over inline source_file', () => {
    expect(
      processedItemSourceLabel({
        source_file: 'inline:json',
        input_preview: 'First few words of the story…',
      }),
    ).toBe('First few words of the story…')
  })

  it('uses basename for S3 paths', () => {
    expect(
      processedItemSourceLabel({
        source_file: 'prefix/nested/article.json',
        input_preview: 'ignored for files',
      }),
    ).toBe('article.json')
  })
})
