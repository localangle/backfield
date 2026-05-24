import { describe, expect, it } from 'vitest'
import {
  getMergedRowPersistedLocationId,
  getMergedRowStylebookCanonicalId,
  isMergedRowLinkedToStylebook,
  isReviewOnlyMergedRow,
  resolveProcessedItemArticleId,
  resolveStylebookSlugForLinkedRow,
  shouldShowAdoptForStylebook,
} from './reviewRow'

describe('processedItemReviewRow', () => {
  it('reads persisted id and stylebook link', () => {
    const row = {
      persisted_location_id: 42,
      stylebook_location_canonical_id: 'uuid-1',
      stylebook_link: {
        label: 'City Hall',
        has_geometry: true,
        geometry_differs: true,
      },
      location: {
        geocode: { result: { geometry: { type: 'Point', coordinates: [1, 2] } } },
      },
    }
    expect(getMergedRowPersistedLocationId(row)).toBe(42)
    expect(getMergedRowStylebookCanonicalId(row)).toBe('uuid-1')
    expect(isMergedRowLinkedToStylebook(row)).toBe(true)
    expect(isReviewOnlyMergedRow(row)).toBe(false)
    expect(shouldShowAdoptForStylebook(row)).toBe(true)
  })

  it('hides adopt when geometry matches', () => {
    const row = {
      stylebook_location_canonical_id: 'uuid-1',
      stylebook_link: {
        label: 'X',
        has_geometry: true,
        geometry_differs: false,
      },
      location: {
        geocode: { result: { geometry: { type: 'Point', coordinates: [1, 2] } } },
      },
    }
    expect(shouldShowAdoptForStylebook(row)).toBe(false)
  })

  it('treats missing persisted id as review-only', () => {
    expect(isReviewOnlyMergedRow({ anchor: 'a' })).toBe(true)
  })

  it('resolves article id from context then input keys', () => {
    expect(
      resolveProcessedItemArticleId(
        { article_id: 9, body: '', resolution: 'substrate' },
        { input_article_id: 3 },
      ),
    ).toBe(9)
    expect(
      resolveProcessedItemArticleId(
        { article_id: null, body: 'x', resolution: 'inline_fallback' },
        { substrate_article_id: '12' },
      ),
    ).toBe(12)
    expect(resolveProcessedItemArticleId(undefined, {})).toBeNull()
    expect(
      resolveProcessedItemArticleId(
        { article_id: null, body: 'x', resolution: 'inline_fallback' },
        {},
        { stylebook_output: { article_id: 77 } },
      ),
    ).toBe(77)
  })

  it('prefers row stylebook_slug over workspace slug for links', () => {
    const row = {
      stylebook_slug: 'illinois-stylebook',
      stylebook_location_canonical_id: 'uuid-1',
      stylebook_link: { label: 'X', has_geometry: true, geometry_differs: false },
    }
    expect(resolveStylebookSlugForLinkedRow(row, 'default')).toBe('illinois-stylebook')
    expect(resolveStylebookSlugForLinkedRow(row, null)).toBe('illinois-stylebook')
    expect(resolveStylebookSlugForLinkedRow({ anchor: 'a' }, 'default')).toBe('default')
  })
})
