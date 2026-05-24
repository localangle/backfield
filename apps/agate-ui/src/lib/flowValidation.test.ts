import { describe, expect, it } from 'vitest'
import {
  validateFlowInputOutputRules,
  validateGeocodeCatalogSelection,
  validateGraphForSave,
  validateInputConnections,
  validateNoOrphans,
  validateSingleBookends,
  type FlowGraph,
} from './flowValidation'

function graph(overrides: Partial<FlowGraph> & Pick<FlowGraph, 'nodes'>): FlowGraph {
  return {
    edges: [],
    ...overrides,
  }
}

describe('validateSingleBookends', () => {
  it('passes with one input and one output bookend', () => {
    const result = validateSingleBookends(
      graph({
        nodes: [
          { id: 'in', type: 'TextInput' },
          { id: 'out', type: 'Output' },
        ],
      }),
    )
    expect(result.ok).toBe(true)
  })

  it('fails with zero input bookends', () => {
    const result = validateSingleBookends(
      graph({
        nodes: [{ id: 'out', type: 'DBOutput' }],
      }),
    )
    expect(result).toMatchObject({
      ok: false,
      title: 'Missing content source',
    })
  })

  it('fails with two input bookends', () => {
    const result = validateSingleBookends(
      graph({
        nodes: [
          { id: 'a', type: 'TextInput' },
          { id: 'b', type: 'JSONInput' },
          { id: 'out', type: 'Output' },
        ],
      }),
    )
    expect(result).toMatchObject({
      ok: false,
      title: 'Too many content sources',
    })
  })

  it('fails with zero output bookends', () => {
    const result = validateSingleBookends(
      graph({
        nodes: [{ id: 'in', type: 'S3Input' }],
      }),
    )
    expect(result).toMatchObject({
      ok: false,
      title: 'Missing results destination',
    })
  })

  it('fails with two output bookends', () => {
    const result = validateSingleBookends(
      graph({
        nodes: [
          { id: 'in', type: 'TextInput' },
          { id: 'a', type: 'Output' },
          { id: 'b', type: 'DBOutput' },
        ],
      }),
    )
    expect(result).toMatchObject({
      ok: false,
      title: 'Too many outputs',
    })
  })
})

describe('validateFlowInputOutputRules', () => {
  it('fails when S3 and API input are both present', () => {
    const result = validateFlowInputOutputRules(
      graph({
        nodes: [
          { id: 's3', type: 'S3Input' },
          { id: 'api', type: 'APIInput' },
          { id: 'out', type: 'Output' },
        ],
      }),
    )
    expect(result).toMatchObject({ ok: false, severity: 'error' })
  })

  it('fails when API input has incoming edge', () => {
    const result = validateFlowInputOutputRules(
      graph({
        nodes: [
          { id: 'in', type: 'TextInput' },
          { id: 'api', type: 'APIInput' },
          { id: 'mid', type: 'PlaceExtract' },
          { id: 'out', type: 'Output' },
        ],
        edges: [{ source: 'mid', target: 'api' }],
      }),
    )
    expect(result).toMatchObject({
      ok: false,
      title: 'API input must come first',
    })
  })
})

describe('validateNoOrphans', () => {
  it('fails when a node has no edges', () => {
    const result = validateNoOrphans(
      graph({
        nodes: [
          { id: 'in', type: 'TextInput' },
          { id: 'lonely', type: 'PlaceExtract' },
          { id: 'out', type: 'Output' },
        ],
        edges: [
          { source: 'in', target: 'out' },
        ],
      }),
    )
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.description).toContain('Place Extract')
      expect(result.description).not.toContain('lonely')
    }
  })
})

describe('validateInputConnections', () => {
  it('fails when a processing node has no incoming edge', () => {
    const result = validateInputConnections(
      graph({
        nodes: [
          { id: 'in', type: 'TextInput' },
          { id: 'pe', type: 'PlaceExtract' },
          { id: 'out', type: 'Output' },
        ],
        edges: [{ source: 'in', target: 'out' }],
      }),
    )
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.description).toContain('Place Extract')
    }
  })

  it('passes when processing nodes receive input', () => {
    const result = validateInputConnections(
      graph({
        nodes: [
          { id: 'in', type: 'TextInput' },
          { id: 'pe', type: 'PlaceExtract' },
          { id: 'out', type: 'Output' },
        ],
        edges: [
          { source: 'in', target: 'pe' },
          { source: 'pe', target: 'out' },
        ],
      }),
    )
    expect(result.ok).toBe(true)
  })
})

describe('validateGeocodeCatalogSelection', () => {
  it('fails when cache is on without catalog', () => {
    const result = validateGeocodeCatalogSelection([
      {
        id: 'g',
        type: 'GeocodeAgent',
        data: { useCache: true },
      },
    ])
    expect(result.ok).toBe(false)
  })

  it('passes when cache is off', () => {
    const result = validateGeocodeCatalogSelection([
      {
        id: 'g',
        type: 'GeocodeAgent',
        data: { useCache: false },
      },
    ])
    expect(result.ok).toBe(true)
  })

  it('passes when cache is on with stylebook_id', () => {
    const result = validateGeocodeCatalogSelection([
      {
        id: 'g',
        type: 'GeocodeAgent',
        data: { useCache: true, stylebook_id: 42 },
      },
    ])
    expect(result.ok).toBe(true)
  })
})

describe('validateGraphForSave', () => {
  it('passes for a valid single-bookend starter graph', () => {
    const result = validateGraphForSave(
      graph({
        nodes: [
          { id: 'in', type: 'TextInput' },
          { id: 'pe', type: 'PlaceExtract' },
          { id: 'out', type: 'Output' },
        ],
        edges: [
          { source: 'in', target: 'pe' },
          { source: 'pe', target: 'out' },
        ],
      }),
    )
    expect(result.ok).toBe(true)
  })
})
