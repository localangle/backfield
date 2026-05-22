import { describe, expect, it } from 'vitest'
import {
  applyPlaceEditFields,
  buildPlaceEditOverlayPatch,
  buildPlaceFieldsOnlyOverlayPatch,
  placeEditFieldsEqual,
  readPlaceEditFields,
} from './processedItemPlaceEditFields'

describe('readPlaceEditFields', () => {
  it('falls back to description when role_in_story is missing', () => {
    const fields = readPlaceEditFields({
      location: { full: 'Ohio' },
      description: 'Christofferson has been held in jail in Ohio since his arrest.',
      original_text: 'Ohio',
    })
    expect(fields.roleInStory).toBe('Christofferson has been held in jail in Ohio since his arrest.')
  })

  it('reads label from location.full and mention from original_text', () => {
    const fields = readPlaceEditFields({
      location: { full: 'Austin, TX' },
      type: 'city',
      original_text: 'Austin',
      role_in_story: 'Scene of protest',
      geocode: { result: { formatted_address: 'Austin, TX, USA' } },
    })
    expect(fields.label).toBe('Austin, TX')
    expect(fields.type).toBe('city')
    expect(fields.mentionText).toBe('Austin')
    expect(fields.roleInStory).toBe('Scene of protest')
    expect(fields.formattedAddress).toBe('Austin, TX, USA')
  })
})

describe('buildPlaceFieldsOnlyOverlayPatch', () => {
  it('omits geocode when only label changes on a complex place', () => {
    const base = {
      location: { full: 'Chicago' },
      type: 'city',
      geocode: {
        result: {
          formatted_address: 'Chicago, IL',
          geometry: {
            type: 'Polygon',
            coordinates: [
              Array.from({ length: 500 }, (_, i) => [i * 0.01, 41.8 + i * 0.001]),
            ],
          },
        },
      },
    }
    const patch = buildPlaceFieldsOnlyOverlayPatch(base, {
      label: 'Chicago, IL',
      type: 'city',
      formattedAddress: 'Chicago, IL',
      roleInStory: '',
      mentionText: '',
      occurrences: [],
    })
    expect(patch.geocode).toBeUndefined()
    expect((patch.location as Record<string, unknown>).full).toBe('Chicago, IL')
  })

  it('includes address-only geocode patch without geometry when address changes', () => {
    const base = {
      location: { full: 'Chicago' },
      geocode: {
        geocode_type: 'pelias',
        result: {
          formatted_address: 'Old',
          geometry: { type: 'Point', coordinates: [0, 0] },
        },
      },
    }
    const patch = buildPlaceFieldsOnlyOverlayPatch(base, {
      label: 'Chicago',
      type: '',
      formattedAddress: 'New addr',
      roleInStory: '',
      mentionText: '',
      occurrences: [],
    })
    const res = (patch.geocode as Record<string, unknown>).result as Record<string, unknown>
    expect(res.formatted_address).toBe('New addr')
    expect(res.geometry).toBeUndefined()
  })
})

describe('buildPlaceEditOverlayPatch', () => {
  it('includes geocode with updated geometry and formatted address', () => {
    const base = {
      location: { full: 'Old' },
      type: 'place',
      geocode: {
        geocode_type: 'pelias',
        result: {
          formatted_address: 'Old addr',
          geometry: { type: 'Point', coordinates: [0, 0] },
        },
      },
    }
    const patch = buildPlaceEditOverlayPatch(
      base,
      {
        label: 'New label',
        type: 'city',
        formattedAddress: 'New addr',
        roleInStory: 'Role',
        mentionText: 'Mention',
        occurrences: [{ clientId: 'c1', mentionText: 'Mention', startChar: null, endChar: null, occurrenceOrder: 0, suppressed: false }],
      },
      { type: 'Point', coordinates: [-97.7, 30.3] },
    )
    expect(patch.type).toBe('city')
    expect(patch.original_text).toBe('Mention')
    const gc = patch.geocode as Record<string, unknown>
    const res = gc.result as Record<string, unknown>
    expect(res.geometry).toEqual({ type: 'Point', coordinates: [-97.7, 30.3] })
    expect(res.formatted_address).toBe('New addr')
    expect(gc.geocode_type).toBe('manual')
    expect(patch.geocoded).toBe(true)
  })

  it('assigns manual geocode and clears QA flags for needs-review failure rows', () => {
    const base = {
      id: 'non-geocoded:republic-steel',
      geocoded: false,
      reason: 'Geocoding produced no result',
      original_text: 'Republic Steel',
      location: 'Republic Steel plant',
      type: 'place',
      description: 'Republic Steel site',
    }
    const patch = buildPlaceEditOverlayPatch(
      base,
      {
        label: 'Republic Steel',
        type: 'place',
        formattedAddress: '',
        roleInStory: '',
        mentionText: 'Republic Steel',
        occurrences: [],
      },
      { type: 'Point', coordinates: [-87.6, 41.7] },
    )
    expect(patch.geocoded).toBe(true)
    expect(patch.reason).toBeUndefined()
    expect(patch.geocode_qa_code).toBeUndefined()
    const gc = patch.geocode as Record<string, unknown>
    expect(gc.geocode_type).toBe('manual')
    const res = gc.result as Record<string, unknown>
    expect(res.geometry).toEqual({ type: 'Point', coordinates: [-87.6, 41.7] })
  })
})

describe('placeEditFieldsEqual', () => {
  it('detects label changes', () => {
    const a = readPlaceEditFields({ description: 'A' })
    const b = { ...a, label: 'B' }
    expect(placeEditFieldsEqual(a, b)).toBe(false)
  })
})

describe('applyPlaceEditFields', () => {
  it('updates location.full when present', () => {
    const out = applyPlaceEditFields({ location: { full: 'X' } }, {
      label: 'Y',
      type: '',
      formattedAddress: '',
      roleInStory: '',
      mentionText: '',
      occurrences: [],
    })
    expect((out.location as Record<string, unknown>).full).toBe('Y')
  })
})
