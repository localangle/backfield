import { describe, expect, it } from 'vitest'
import {
  appendUserPlacePoint,
  buildGeocodePatchForGeometry,
  extractGeometryFromPlace,
  iterBaselinePlacesFromOutput,
  shallowMergePlacePatch,
  validateGeometryObject,
} from './processedItemPlaceGeometry'

describe('iterBaselinePlacesFromOutput', () => {
  it('iterates node locations with anchors', () => {
    const rows = iterBaselinePlacesFromOutput({
      n1: { locations: [{ id: 'a1', description: 'x' }] },
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].anchor).toBe('a1')
  })
})

describe('extractGeometryFromPlace', () => {
  it('reads geocode.result.geometry', () => {
    const g = extractGeometryFromPlace({
      geocode: { result: { geometry: { type: 'Point', coordinates: [1, 2] } } },
    })
    expect(g).toEqual({ type: 'Point', coordinates: [1, 2] })
  })
})

describe('buildGeocodePatchForGeometry', () => {
  it('preserves geocode_type when present', () => {
    const merged = {
      geocode: { geocode_type: 'pelias', result: { formatted_address: 'X', geometry: { type: 'Point', coordinates: [0, 0] } } },
    }
    const patch = buildGeocodePatchForGeometry(merged as Record<string, unknown>, {
      type: 'Point',
      coordinates: [3, 4],
    })
    expect((patch.geocode as Record<string, unknown>).geocode_type).toBe('pelias')
    expect(((patch.geocode as Record<string, unknown>).result as Record<string, unknown>).geometry).toEqual({
      type: 'Point',
      coordinates: [3, 4],
    })
  })
})

describe('shallowMergePlacePatch', () => {
  it('merges top-level keys', () => {
    expect(shallowMergePlacePatch({ a: 1 }, { b: 2 })).toEqual({ a: 1, b: 2 })
  })
})

describe('validateGeometryObject', () => {
  it('rejects out-of-range lng', () => {
    expect(validateGeometryObject({ type: 'Point', coordinates: [200, 0] })).toMatch(/range/)
  })

  it('accepts valid point', () => {
    expect(validateGeometryObject({ type: 'Point', coordinates: [-90, 44] })).toBeNull()
  })
})

describe('appendUserPlacePoint', () => {
  it('adds user_place row', () => {
    const draft: Record<string, unknown> = {}
    const id = appendUserPlacePoint(draft, -93, 45, 'Hi')
    expect(id.startsWith('user_place:')).toBe(true)
    const loc = draft.locations as Record<string, unknown>
    const ua = loc.user_added as unknown[]
    expect(Array.isArray(ua) && ua.length).toBe(1)
  })
})
