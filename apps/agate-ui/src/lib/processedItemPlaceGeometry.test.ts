import { describe, expect, it } from 'vitest'
import {
  appendUserPlacePoint,
  buildGeocodePatchForGeometry,
  buildVerificationLeafletCollections,
  extractGeometryFromPlace,
  stripSelectedVerificationPolygonsForEdit,
  getGeocodedPlaceDisplay,
  getGeocodingSourceLabel,
  getPlaceEditorialDetail,
  placeEditorialDetailHasContent,
  isGeocodedPlace,
  iterBaselinePlacesFromOutput,
  leafletBoundsFromGeometry,
  shallowMergePlacePatch,
  validateGeometryObject,
} from './processedItemPlaceGeometry'

describe('iterBaselinePlacesFromOutput', () => {
  it('returns empty when output has only PlaceExtract locations', () => {
    const rows = iterBaselinePlacesFromOutput({
      place_extract: { locations: [{ id: 'a1', description: 'x' }] },
    })
    expect(rows).toHaveLength(0)
  })

  it('iterates geocoded places with anchors', () => {
    const rows = iterBaselinePlacesFromOutput({
      geocode_agent: {
        places: {
          areas: { states: [], counties: [], cities: [{ id: 'a1', description: 'x' }], neighborhoods: [], regions: [], other: [] },
          points: [],
        },
      },
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].anchor).toBe('a1')
  })

  it('ignores PlaceExtract locations when a sibling node has geocoded places', () => {
    const rows = iterBaselinePlacesFromOutput({
      place_extract: {
        locations: [{ id: 'extract:2', description: 'pre-geocode hospital' }],
      },
      geocode_agent: {
        places: {
          points: [
            {
              id: 'h3:hospital',
              description: 'Presence St. Francis Hospital',
              geocode: { result: { geometry: { type: 'Point', coordinates: [-87.68, 42.02] } } } },
            },
          ],
        },
      },
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].nodeId).toBe('geocode_agent')
    expect((rows[0].location as { description?: string }).description).toBe('Presence St. Francis Hospital')
  })

  it('prefers stylebook_output places over geocode_agent', () => {
    const rows = iterBaselinePlacesFromOutput({
      geocode_agent: {
        places: { points: [{ id: 'geo', description: 'from geocode' }] },
      },
      stylebook_output: {
        places: { points: [{ id: 'sb', description: 'from stylebook' }] },
      },
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].nodeId).toBe('stylebook_output')
    expect((rows[0].location as { description?: string }).description).toBe('from stylebook')
  })

  it('skips locations array when the same node has places', () => {
    const rows = iterBaselinePlacesFromOutput({
      geocode_agent: {
        locations: [
          { id: 'extract-only', description: 'pre-geocode' },
        ],
        places: {
          points: [
            {
              id: 'h3:cell',
              description: 'geocoded',
              geocode: { result: { geometry: { type: 'Point', coordinates: [1, 2] } } } },
            },
          ],
        },
      },
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].anchor).toBe('geocode_agent:0')
    expect(rows.some((r) => r.anchor === 'extract-only')).toBe(false)
  })

  it('does not collapse colocated points that share an h3 id', () => {
    const h3 = 'h3:8c2664cacb6ddff'
    const rows = iterBaselinePlacesFromOutput({
      geo: {
        places: {
          points: [
            {
              id: h3,
              description: 'Salt Shed',
              geocode: { result: { geometry: { type: 'Point', coordinates: [1, 2] } } } },
            },
            {
              id: h3,
              description: 'Oddball Market',
              geocode: { result: { geometry: { type: 'Point', coordinates: [1, 2] } } } },
            },
          ],
        },
      },
    })
    expect(rows.map((r) => r.anchor).sort()).toEqual(['geo:0', 'geo:1'])
  })
})

describe('isGeocodedPlace', () => {
  it('is true when geocode result has geometry', () => {
    expect(
      isGeocodedPlace({
        geocode: { result: { geometry: { type: 'Point', coordinates: [1, 2] } } },
      }),
    ).toBe(true)
  })

  it('is false for place extract only', () => {
    expect(isGeocodedPlace({ description: 'x', location: { full: 'A' } })).toBe(false)
  })
})

describe('getPlaceEditorialDetail', () => {
  it('prefers role_in_story over description', () => {
    expect(
      getPlaceEditorialDetail({
        role_in_story: 'Scene of the crash',
        description: 'Longer editorial sentence',
        nature: 'primary',
        nature_secondary_tags: ['context'],
      }),
    ).toEqual({
      roleInStory: 'Scene of the crash',
      nature: 'primary',
      natureSecondaryTags: ['context'],
    })
  })

  it('falls back to description when role_in_story is missing', () => {
    expect(
      getPlaceEditorialDetail({
        description: 'Where the parade happened',
        nature: 'subject',
      }),
    ).toEqual({
      roleInStory: 'Where the parade happened',
      nature: 'subject',
      natureSecondaryTags: [],
    })
  })
})

describe('placeEditorialDetailHasContent', () => {
  it('is false when all fields empty', () => {
    expect(placeEditorialDetailHasContent(getPlaceEditorialDetail(null))).toBe(false)
  })
})

describe('getGeocodedPlaceDisplay', () => {
  it('reads name, type, address, and nature as role', () => {
    expect(
      getGeocodedPlaceDisplay({
        location: 'Dublin, Ireland',
        type: 'city',
        nature: 'primary',
        geocode: { result: { formatted_address: 'Dublin, County Dublin, Ireland' } },
      }),
    ).toEqual({
      name: 'Dublin, Ireland',
      type: 'city',
      formattedAddress: 'Dublin, County Dublin, Ireland',
      role: 'primary',
    })
  })
})

describe('leafletBoundsFromGeometry', () => {
  it('pads a point', () => {
    const b = leafletBoundsFromGeometry({ type: 'Point', coordinates: [-93, 45] })
    expect(b).not.toBeNull()
    expect(b![0][0]).toBeLessThan(45)
    expect(b![1][0]).toBeGreaterThan(45)
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

describe('getGeocodingSourceLabel', () => {
  it('maps geocode_type to user-facing labels', () => {
    expect(
      getGeocodingSourceLabel({
        geocode: { geocode_type: 'pelias_search', result: { formatted_address: 'X' } },
      }),
    ).toBe('Address search')
    expect(
      getGeocodingSourceLabel({
        geocode: { geocode_type: 'geocodio_structured', result: {} },
      }),
    ).toBe('Geocodio')
    expect(
      getGeocodingSourceLabel({
        geocode: { geocode_type: 'manual', result: {} },
      }),
    ).toBe('Manual')
  })

  it('prefers manual over Stylebook confidence after map edit', () => {
    expect(
      getGeocodingSourceLabel({
        geocode: {
          geocode_type: 'manual',
          result: { confidence: { source: 'canonical_db', canonical_id: 'x' } },
        },
      }),
    ).toBe('Manual')
  })

  it('uses confidence.source when geocode_type is missing', () => {
    expect(
      getGeocodingSourceLabel({
        geocode: { result: { confidence: { source: 'location_cache' } } },
      }),
    ).toBe('Saved geocode')
  })

  it('returns null when no geocode metadata', () => {
    expect(getGeocodingSourceLabel({ description: 'Nowhere' })).toBeNull()
  })
})

describe('buildGeocodePatchForGeometry', () => {
  it('marks geocode as manual when geometry is edited on the map', () => {
    const merged = {
      geocode: {
        geocode_type: 'stylebook',
        result: {
          formatted_address: 'X',
          geometry: { type: 'Point', coordinates: [0, 0] },
          confidence: { source: 'canonical_db', canonical_id: 'c1' },
        },
      },
    }
    const patch = buildGeocodePatchForGeometry(merged as Record<string, unknown>, {
      type: 'Point',
      coordinates: [3, 4],
    })
    const gc = patch.geocode as Record<string, unknown>
    expect(gc.geocode_type).toBe('manual')
    expect(((gc.result as Record<string, unknown>).confidence as Record<string, unknown>).source).toBe(
      'manual',
    )
    expect(((gc.result as Record<string, unknown>).geometry as Record<string, unknown>)).toEqual({
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

describe('buildVerificationLeafletCollections', () => {
  it('skips region-mismatch needs_review rows on the map', () => {
    const collections = buildVerificationLeafletCollections({
      mergedRows: [
        {
          anchor: 'bad',
          location: {
            description: 'Republic Steel',
            geocode_qa_code: 'geocode_region_mismatch',
            geocode: {
              result: {
                geometry: { type: 'Point', coordinates: [105, 35] },
              },
            },
          },
        },
      ],
      baselineByAnchor: new Map(),
      selectedAnchor: null,
    })
    expect(collections.places.features).toHaveLength(0)
  })
  const pointRow = (anchor: string, lng: number, lat: number) => ({
    anchor,
    location: {
      description: anchor,
      geocode: { result: { geometry: { type: 'Point', coordinates: [lng, lat] } } },
    },
  })

  it('includes all places when nothing is selected', () => {
    const collections = buildVerificationLeafletCollections({
      mergedRows: [pointRow('a1', -93, 45), pointRow('a2', -90, 44)],
      baselineByAnchor: new Map(),
      selectedAnchor: null,
    })
    expect(collections.points.features).toHaveLength(2)
  })

  it('includes only the selected place when one is selected', () => {
    const collections = buildVerificationLeafletCollections({
      mergedRows: [pointRow('a1', -93, 45), pointRow('a2', -90, 44)],
      baselineByAnchor: new Map(),
      selectedAnchor: 'a2',
    })
    expect(collections.points.features).toHaveLength(1)
    expect(collections.points.features[0]?.id).toBe('a2')
  })

  it('shows only draft geometry while editing a linked place', () => {
    const anchor = 'illinois'
    const baseline = {
      description: anchor,
      stylebook_location_canonical_id: 'canon-1',
      geocode: {
        result: {
          geometry: {
            type: 'Polygon',
            coordinates: [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
          },
        },
      },
    }
    const merged = {
      anchor,
      location: {
        ...baseline,
        geocode: {
          result: {
            geometry: {
              type: 'Polygon',
              coordinates: [[[10, 10], [12, 10], [12, 12], [10, 12], [10, 10]]],
            },
          },
        },
      },
    }
    const viewUnsaved = buildVerificationLeafletCollections({
      mergedRows: [merged],
      baselineByAnchor: new Map([[anchor, baseline]]),
      selectedAnchor: anchor,
      geometryEditing: false,
      unsavedGeometryOverlay: true,
    })
    expect(viewUnsaved.polygons.features).toHaveLength(2)

    const viewSaved = buildVerificationLeafletCollections({
      mergedRows: [merged],
      baselineByAnchor: new Map([[anchor, baseline]]),
      selectedAnchor: anchor,
      geometryEditing: false,
      unsavedGeometryOverlay: false,
    })
    expect(viewSaved.polygons.features).toHaveLength(1)
    expect(viewSaved.polygons.features[0]?.id).toBe(anchor)

    const editing = buildVerificationLeafletCollections({
      mergedRows: [merged],
      baselineByAnchor: new Map([[anchor, baseline]]),
      selectedAnchor: anchor,
      geometryEditing: true,
    })
    expect(editing.polygons.features).toHaveLength(1)
    expect(editing.polygons.features[0]?.id).toBe(anchor)
  })
})

describe('stripSelectedVerificationPolygonsForEdit', () => {
  it('removes selected place polygon layers but keeps points and baseline polygons', () => {
    const collections = buildVerificationLeafletCollections({
      mergedRows: [
        {
          anchor: 'a1',
          location: {
            description: 'a1',
            geocode: { result: { geometry: { type: 'Point', coordinates: [-93, 45] } } },
          },
        },
      ],
      baselineByAnchor: new Map(),
      selectedAnchor: 'a1',
    })
    collections.polygons.features.push({
      type: 'Feature',
      id: 'other',
      properties: { id: 'other', label: 'other', group: 'verification-place' },
      geometry: {
        type: 'Polygon',
        coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
      },
    })
    collections.polygons.features.push({
      type: 'Feature',
      id: 'a1__baseline',
      properties: { id: 'a1__baseline', label: 'baseline', group: 'verification-baseline' },
      geometry: {
        type: 'Polygon',
        coordinates: [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
      },
    })

    const stripped = stripSelectedVerificationPolygonsForEdit(collections, 'a1')
    expect(stripped.points.features).toHaveLength(1)
    expect(stripped.polygons.features.map((f) => (f as { id?: string }).id)).toEqual(['other', 'a1__baseline'])
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
