import { describe, expect, it } from 'vitest'
import { resolveEvidenceSpanInArticle } from './processedItemEvidenceSpan'

describe('resolveEvidenceSpanInArticle', () => {
  it('returns none for empty body', () => {
    expect(resolveEvidenceSpanInArticle('', { original_text: 'hello' })).toEqual({
      kind: 'none',
      reason: 'empty_body',
    })
  })

  it('returns none when location missing', () => {
    expect(resolveEvidenceSpanInArticle('abc', null)).toEqual({ kind: 'none', reason: 'no_evidence' })
  })

  it('uses original_text first occurrence', () => {
    const body = 'We met in Chicago before returning to Chicago.'
    const r = resolveEvidenceSpanInArticle(body, { original_text: 'Chicago' })
    expect(r).toEqual({ kind: 'range', start: 10, end: 17 })
  })

  it('trims original_text for matching', () => {
    const body = 'Hello world'
    expect(resolveEvidenceSpanInArticle(body, { original_text: '  world  ' })).toEqual({
      kind: 'range',
      start: 6,
      end: 11,
    })
  })

  it('returns not_in_story when phrase missing', () => {
    expect(resolveEvidenceSpanInArticle('alpha beta', { original_text: 'gamma' })).toEqual({
      kind: 'none',
      reason: 'not_in_story',
    })
  })

  it('prefers valid components.span start/end over original_text', () => {
    const body = 'abcdefghij'
    const r = resolveEvidenceSpanInArticle(body, {
      original_text: 'wrong',
      components: { span: { start: 2, end: 5 } },
    })
    expect(r).toEqual({ kind: 'range', start: 2, end: 5 })
  })

  it('supports span start + length', () => {
    const body = 'abcdefghij'
    expect(
      resolveEvidenceSpanInArticle(body, {
        components: { span: { start: 1, length: 3 } },
      }),
    ).toEqual({ kind: 'range', start: 1, end: 4 })
  })

  it('invalid_offsets when span end past body and no usable original_text', () => {
    expect(
      resolveEvidenceSpanInArticle('hi', {
        components: { span: { start: 0, end: 10 } },
      }),
    ).toEqual({ kind: 'none', reason: 'invalid_offsets' })
  })

  it('rejects span with start past body', () => {
    expect(
      resolveEvidenceSpanInArticle('hi', {
        components: { span: { start: 5, end: 6 } },
      }),
    ).toEqual({ kind: 'none', reason: 'invalid_offsets' })
  })

  it('falls back to original_text when span invalid', () => {
    const body = 'The car stopped.'
    expect(
      resolveEvidenceSpanInArticle(body, {
        original_text: 'car',
        components: { span: { start: -1, end: 2 } },
      }),
    ).toEqual({ kind: 'range', start: 4, end: 7 })
  })
})
