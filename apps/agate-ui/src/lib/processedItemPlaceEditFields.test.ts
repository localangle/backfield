import { describe, expect, it } from 'vitest'
import {
  applyPlaceEditFields,
  buildPlaceEditOverlayPatch,
  placeEditFieldsEqual,
  readPlaceEditFields,
} from './processedItemPlaceEditFields'

describe('readPlaceEditFields', () => {
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
      },
      { type: 'Point', coordinates: [-97.7, 30.3] },
    )
    expect(patch.type).toBe('city')
    expect(patch.original_text).toBe('Mention')
    const gc = patch.geocode as Record<string, unknown>
    const res = gc.result as Record<string, unknown>
    expect(res.geometry).toEqual({ type: 'Point', coordinates: [-97.7, 30.3] })
    expect(res.formatted_address).toBe('New addr')
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
    })
    expect((out.location as Record<string, unknown>).full).toBe('Y')
  })
})
