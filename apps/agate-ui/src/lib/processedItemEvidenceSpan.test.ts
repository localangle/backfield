import { describe, expect, it } from 'vitest'
import {
  buildMentionSpanHits,
  collectAnchorsForRange,
  findAllMentionOccurrencesInArticle,
  mergeTieredHighlightRanges,
  resolveEvidenceSpanInArticle,
  resolveEvidenceSpansInArticle,
} from './processedItemEvidenceSpan'

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
})

describe('resolveEvidenceSpansInArticle', () => {
  it('returns all original_text occurrences', () => {
    const body = 'We met in Chicago before returning to Chicago.'
    expect(resolveEvidenceSpansInArticle(body, { original_text: 'Chicago' })).toEqual({
      kind: 'ranges',
      ranges: [
        { start: 10, end: 17 },
        { start: 38, end: 45 },
      ],
    })
  })

  it('returns single range for valid components.span', () => {
    const body = 'abcdefghij'
    expect(
      resolveEvidenceSpansInArticle(body, {
        original_text: 'Chicago',
        components: { span: { start: 2, end: 5 } },
      }),
    ).toEqual({ kind: 'ranges', ranges: [{ start: 2, end: 5 }] })
  })
})

describe('findAllMentionOccurrencesInArticle', () => {
  it('collects occurrences for multiple needles', () => {
    const body = 'Alpha in Chicago and beta in Chicago.'
    expect(findAllMentionOccurrencesInArticle(body, ['Chicago', 'Alpha'])).toEqual([
      { start: 0, end: 5 },
      { start: 9, end: 16 },
      { start: 29, end: 36 },
    ])
  })
})

describe('buildMentionSpanHits', () => {
  it('merges anchors that share the same original_text range', () => {
    const body = 'Events in Chicago drew crowds.'
    const hits = buildMentionSpanHits(body, [
      { anchor: 'a1', location: { original_text: 'Chicago' } },
      { anchor: 'a2', location: { original_text: 'Chicago' } },
    ])
    expect(hits).toEqual([{ start: 11, end: 18, anchors: ['a1', 'a2'] }])
  })

  it('keeps separate ranges for separate occurrences', () => {
    const body = 'Chicago to Chicago.'
    const hits = buildMentionSpanHits(body, [{ anchor: 'a1', location: { original_text: 'Chicago' } }])
    expect(hits).toEqual([
      { start: 0, end: 7, anchors: ['a1'] },
      { start: 11, end: 18, anchors: ['a1'] },
    ])
  })
})

describe('collectAnchorsForRange', () => {
  it('returns anchors whose hits overlap the query range', () => {
    const hits = buildMentionSpanHits('Alpha in Chicago.', [
      { anchor: 'a1', location: { original_text: 'Alpha' } },
      { anchor: 'a2', location: { original_text: 'Chicago' } },
    ])
    expect(collectAnchorsForRange(hits, 0, 5)).toEqual(['a1'])
    expect(collectAnchorsForRange(hits, 9, 16)).toEqual(['a2'])
  })
})

describe('mergeTieredHighlightRanges', () => {
  it('prefers selected tier over ambient overlap', () => {
    expect(
      mergeTieredHighlightRanges(
        [{ start: 10, end: 20 }],
        [{ start: 12, end: 18 }],
      ),
    ).toEqual([
      { start: 10, end: 12, tier: 'ambient' },
      { start: 12, end: 18, tier: 'selected' },
      { start: 18, end: 20, tier: 'ambient' },
    ])
  })
})

describe('resolveEvidenceSpanInArticle (continued)', () => {
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
