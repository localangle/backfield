import { describe, expect, it } from 'vitest'
import {
  paramsForGraphSave,
  sanitizeNodeStylebookRef,
  validateCustomExtractRecordTypes,
  validateDocumentChunkerPlacement,
  validateFlowInputOutputRules,
  validateGraphForSave,
  validateInputConnections,
  validateJsonInputNodes,
  validateNoOrphans,
  validateSingleBookends,
  type FlowGraph,
} from './flowValidation'
import { jsonInputInvalidNodeData } from './jsonInputValidation'

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

describe('paramsForGraphSave', () => {
  it('normalizes S3 folder_path to a single trailing slash', () => {
    expect(
      paramsForGraphSave({
        id: 's3',
        type: 'S3Input',
        data: { bucket: 'b', folder_path: 'input/articles///' },
      }).folder_path,
    ).toBe('input/articles/')
  })

  it('normalizes S3 bucket by stripping s3:// on save', () => {
    expect(
      paramsForGraphSave({
        id: 's3',
        type: 'S3Input',
        data: { bucket: 's3://my-bucket', folder_path: 'input/' },
      }).bucket,
    ).toBe('my-bucket')
  })

  it('strips JSON input invalid marker before save', () => {
    expect(
      paramsForGraphSave({
        id: 'json',
        type: 'JSONInput',
        data: jsonInputInvalidNodeData({ text: 'hello' }),
      }),
    ).toEqual({ text: 'hello' })
  })
})

describe('sanitizeNodeStylebookRef', () => {
  const validIds = new Set([10, 20])

  it('clears stale Backfield output stylebook ids', () => {
    expect(
      sanitizeNodeStylebookRef('DBOutput', { stylebook_id: 99 }, validIds, 10),
    ).toEqual({ stylebook_id: null })
  })

  it('remaps stale geocode cache stylebook ids to the org default', () => {
    expect(
      sanitizeNodeStylebookRef(
        'GeocodeAgent',
        { useCache: true, stylebook_id: 99 },
        validIds,
        10,
      ),
    ).toEqual({ useCache: true, stylebook_id: 10 })
  })
})

describe('validateCustomExtractRecordTypes', () => {
  it('passes when custom extract steps use distinct record types', () => {
    const result = validateCustomExtractRecordTypes(
      graph({
        nodes: [
          { id: 'ce1', type: 'CustomExtract', data: { record_type: 'ingredients' } },
          { id: 'ce2', type: 'CustomExtract', data: { record_type: 'steps' } },
        ],
      }),
    )
    expect(result.ok).toBe(true)
  })

  it('ignores custom extract steps without a record type yet', () => {
    const result = validateCustomExtractRecordTypes(
      graph({
        nodes: [
          { id: 'ce1', type: 'CustomExtract', data: { record_type: '' } },
          { id: 'ce2', type: 'CustomExtract' },
        ],
      }),
    )
    expect(result.ok).toBe(true)
  })

  it('warns when two custom extract steps share a record type', () => {
    const result = validateCustomExtractRecordTypes(
      graph({
        nodes: [
          { id: 'ce1', type: 'CustomExtract', data: { record_type: 'ingredients' } },
          { id: 'ce2', type: 'CustomExtract', data: { record_type: 'ingredients' } },
        ],
      }),
    )
    expect(result).toMatchObject({
      ok: false,
      title: 'Custom Extract steps overlap',
      severity: 'warning',
    })
    if (!result.ok) {
      expect(result.description).toContain('ingredients')
    }
  })
})

describe('validateDocumentChunkerPlacement', () => {
  it('passes when Document Chunker sits directly after the content source', () => {
    const result = validateDocumentChunkerPlacement(
      graph({
        nodes: [
          { id: 'in', type: 'TextInput' },
          { id: 'chunk', type: 'DocumentChunker' },
          { id: 'pe', type: 'PlaceExtract' },
          { id: 'out', type: 'Output' },
        ],
        edges: [
          { source: 'in', target: 'chunk' },
          { source: 'chunk', target: 'pe' },
          { source: 'pe', target: 'out' },
        ],
      }),
    )
    expect(result.ok).toBe(true)
  })

  it('rejects more than one Document Chunker', () => {
    const result = validateDocumentChunkerPlacement(
      graph({
        nodes: [
          { id: 'in', type: 'TextInput' },
          { id: 'c1', type: 'DocumentChunker' },
          { id: 'c2', type: 'DocumentChunker' },
          { id: 'out', type: 'Output' },
        ],
        edges: [
          { source: 'in', target: 'c1' },
          { source: 'c1', target: 'c2' },
          { source: 'c2', target: 'out' },
        ],
      }),
    )
    expect(result).toMatchObject({
      ok: false,
      title: 'Too many Document Chunkers',
      severity: 'error',
    })
  })

  it('rejects a bypass branch that skips Document Chunker', () => {
    const result = validateDocumentChunkerPlacement(
      graph({
        nodes: [
          { id: 'in', type: 'TextInput' },
          { id: 'chunk', type: 'DocumentChunker' },
          { id: 'pe', type: 'PlaceExtract' },
          { id: 'out', type: 'Output' },
        ],
        edges: [
          { source: 'in', target: 'chunk' },
          { source: 'in', target: 'pe' },
          { source: 'chunk', target: 'out' },
          { source: 'pe', target: 'out' },
        ],
      }),
    )
    expect(result).toMatchObject({
      ok: false,
      title: 'Document Chunker placement',
      severity: 'error',
    })
    if (!result.ok) {
      expect(result.description).toMatch(/every step after the content source/i)
    }
  })

  it('rejects Document Chunker not connected from the content source', () => {
    const result = validateDocumentChunkerPlacement(
      graph({
        nodes: [
          { id: 'in', type: 'TextInput' },
          { id: 'pe', type: 'PlaceExtract' },
          { id: 'chunk', type: 'DocumentChunker' },
          { id: 'out', type: 'Output' },
        ],
        edges: [
          { source: 'in', target: 'pe' },
          { source: 'pe', target: 'chunk' },
          { source: 'chunk', target: 'out' },
        ],
      }),
    )
    expect(result).toMatchObject({
      ok: false,
      title: 'Document Chunker placement',
      severity: 'error',
    })
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

  it('fails save when Document Chunker placement is invalid', () => {
    const result = validateGraphForSave(
      graph({
        nodes: [
          { id: 'in', type: 'TextInput' },
          { id: 'chunk', type: 'DocumentChunker' },
          { id: 'pe', type: 'PlaceExtract' },
          { id: 'out', type: 'Output' },
        ],
        edges: [
          { source: 'in', target: 'chunk' },
          { source: 'in', target: 'pe' },
          { source: 'chunk', target: 'out' },
          { source: 'pe', target: 'out' },
        ],
      }),
    )
    expect(result).toMatchObject({
      ok: false,
      title: 'Document Chunker placement',
      severity: 'error',
    })
  })

  it('passes for S3 Input when the bucket name includes s3://', () => {
    const result = validateGraphForSave(
      graph({
        nodes: [
          { id: 's3', type: 'S3Input', data: { bucket: 's3://my-bucket' } },
          { id: 'out', type: 'Output' },
        ],
        edges: [{ source: 's3', target: 'out' }],
      }),
    )
    expect(result.ok).toBe(true)
  })

  it('fails when JSON input has an invalid editor marker', () => {
    const result = validateGraphForSave(
      graph({
        nodes: [
          {
            id: 'json',
            type: 'JSONInput',
            data: jsonInputInvalidNodeData({ text: 'hello' }),
          },
          { id: 'out', type: 'Output' },
        ],
        edges: [{ source: 'json', target: 'out' }],
      }),
    )
    expect(result).toMatchObject({ ok: false, severity: 'error', title: 'Invalid JSON input' })
  })
})

describe('validateJsonInputNodes', () => {
  it('accepts valid JSON input params', () => {
    expect(
      validateJsonInputNodes([{ id: 'json', type: 'JSONInput', data: { text: '' } }]).ok,
    ).toBe(true)
  })

  it('rejects missing text field', () => {
    expect(
      validateJsonInputNodes([{ id: 'json', type: 'JSONInput', data: { headline: 'Hi' } }]),
    ).toMatchObject({ ok: false })
  })
})
