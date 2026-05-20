import { describe, expect, it } from 'vitest'
import {
  applyDescriptionPatch,
  buildRemovePlaceOverlayPatch,
  deepSortKeys,
  emptyOverlay,
  getLocationDescription,
  getStylebookCanonicalHandoffId,
  isApiConflictError,
  isLocationLinkedToStylebookCanonical,
  normalizeOverlay,
  overlaysStructurallyEqual,
} from './processedItemVerificationOverlay'

describe('normalizeOverlay', () => {
  it('fills missing locations shape', () => {
    const o = normalizeOverlay(null)
    expect(o.locations).toEqual({ by_anchor: {}, user_added: [], removed_anchors: [] })
  })

  it('preserves by_anchor and user_added', () => {
    const raw = {
      locations: {
        by_anchor: { a: { description: 'x' } },
        user_added: [{ id: 'user_place:u1', location: { description: 'y' } }],
      },
    }
    const o = normalizeOverlay(raw)
    expect((o.locations as { by_anchor: Record<string, unknown> }).by_anchor.a).toEqual({
      description: 'x',
    })
    expect(Array.isArray((o.locations as { user_added: unknown[] }).user_added)).toBe(true)
  })
})

describe('overlaysStructurallyEqual', () => {
  it('ignores key order', () => {
    const a = { locations: { user_added: [], by_anchor: { z: { description: '1' } } } }
    const b = { locations: { by_anchor: { z: { description: '1' } }, user_added: [] } }
    expect(overlaysStructurallyEqual(a, b)).toBe(true)
  })
})

describe('applyDescriptionPatch', () => {
  it('merges description into by_anchor', () => {
    const draft = normalizeOverlay(null)
    applyDescriptionPatch(draft, 'mid', 'edited')
    const by = (draft.locations as { by_anchor: Record<string, unknown> }).by_anchor
    expect(by.mid).toEqual({ description: 'edited' })
  })
})

describe('isLocationLinkedToStylebookCanonical', () => {
  it('detects geocode.result.canonical_id', () => {
    expect(
      isLocationLinkedToStylebookCanonical({
        description: 'x',
        geocode: { result: { canonical_id: 'uuid-here' } },
      }),
    ).toBe(true)
  })

  it('detects stylebook_location_canonical_id string', () => {
    expect(
      isLocationLinkedToStylebookCanonical({
        stylebook_location_canonical_id: '12',
      }),
    ).toBe(true)
  })

  it('returns false when unlinked', () => {
    expect(
      isLocationLinkedToStylebookCanonical({
        description: 'Minneapolis',
        geocode: { result: { formatted_address: 'Minneapolis, MN' } },
      }),
    ).toBe(false)
  })
})

describe('getStylebookCanonicalHandoffId', () => {
  it('prefers stylebook_location_canonical_id string', () => {
    expect(getStylebookCanonicalHandoffId({ stylebook_location_canonical_id: '  uuid-1  ' })).toBe('uuid-1')
  })

  it('reads canonical_id from geocode result', () => {
    expect(
      getStylebookCanonicalHandoffId({
        geocode: { result: { canonical_id: 'uuid-2' } },
      }),
    ).toBe('uuid-2')
  })

  it('returns null when absent', () => {
    expect(getStylebookCanonicalHandoffId({ description: 'x' })).toBe(null)
  })
})

describe('getLocationDescription', () => {
  it('reads description string', () => {
    expect(getLocationDescription({ description: 'Hello' })).toBe('Hello')
  })
})

describe('isApiConflictError', () => {
  it('detects 409 in Error message', () => {
    expect(isApiConflictError(new Error('API error: 409 - {}'))).toBe(true)
    expect(isApiConflictError(new Error('API error: 404 - {}'))).toBe(false)
  })
})

describe('deepSortKeys', () => {
  it('sorts object keys recursively', () => {
    expect(deepSortKeys({ b: 1, a: { d: 2, c: 3 } })).toEqual({ a: { c: 3, d: 2 }, b: 1 })
  })
})

describe('emptyOverlay', () => {
  it('returns stable shape', () => {
    expect(emptyOverlay()).toEqual({
      locations: { by_anchor: {}, user_added: [], removed_anchors: [] },
    })
  })
})

describe('buildRemovePlaceOverlayPatch', () => {
  it('adds removed_anchors for model rows', () => {
    const draft = normalizeOverlay({
      locations: { by_anchor: { a1: { description: 'x' } }, user_added: [] },
    })
    const next = buildRemovePlaceOverlayPatch(draft, 'a1', 'model')
    const loc = next.locations as {
      removed_anchors: string[]
      by_anchor: Record<string, unknown>
    }
    expect(loc.removed_anchors).toEqual(['a1'])
    expect(loc.by_anchor.a1).toBeUndefined()
  })

  it('drops user_added row by id', () => {
    const draft = normalizeOverlay({
      locations: {
        by_anchor: {},
        user_added: [{ id: 'user_place:u1', location: { description: 'y' } }],
      },
    })
    const next = buildRemovePlaceOverlayPatch(draft, 'user_place:u1', 'user')
    const loc = next.locations as { user_added: unknown[] }
    expect(loc.user_added).toEqual([])
  })
})
