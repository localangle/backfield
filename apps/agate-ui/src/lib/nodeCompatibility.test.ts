import { describe, expect, it } from 'vitest'
import {
  getCompatibleInsertNodes,
  getCompatibleNextNodes,
  resolveEdgeHandles,
} from './nodeCompatibility'

describe('getCompatibleNextNodes', () => {
  it('enables Place Extract and disables Geocode from Text Input ancestry', () => {
    const result = getCompatibleNextNodes('TextInput', ['TextInput'])
    expect(result.enabled.map((e) => e.type)).toContain('PlaceExtract')
    expect(result.enabled.map((e) => e.type)).not.toContain('GeocodeAgent')

    const geocode = result.disabled.find((e) => e.type === 'GeocodeAgent')
    expect(geocode).toBeDefined()
    expect(geocode?.reason).toMatch(/extracted places/i)
  })

  it('enables Geocode after Place Extract is in branch ancestry', () => {
    const result = getCompatibleNextNodes('PlaceExtract', ['TextInput', 'PlaceExtract'])
    expect(result.enabled.map((e) => e.type)).toContain('GeocodeAgent')
  })

  it('never offers output bookend types', () => {
    const result = getCompatibleNextNodes('TextInput', ['TextInput'])
    const allTypes = [...result.enabled, ...result.disabled].map((e) => e.type)
    expect(allTypes).not.toContain('Output')
    expect(allTypes).not.toContain('DBOutput')
  })

  it('includes helper text on disabled Geocode before Place Extract exists', () => {
    const result = getCompatibleNextNodes('TextInput', ['TextInput'])
    const geocode = result.disabled.find((e) => e.type === 'GeocodeAgent')
    expect(geocode?.reason).toBe('Requires extracted places as input.')
  })

  it('enables Person and Place Extract from JSON Input', () => {
    const result = getCompatibleNextNodes('JSONInput', ['JSONInput'])
    expect(result.enabled.map((e) => e.type)).toContain('PlaceExtract')
    expect(result.enabled.map((e) => e.type)).toContain('PersonExtract')
  })

  it('enables Article Metadata from JSON Input when generative models are available', () => {
    const result = getCompatibleNextNodes('JSONInput', ['JSONInput'], {
      projectModelCapabilities: { generative: true },
    })
    expect(result.enabled.map((e) => e.type)).toContain('ArticleMetadata')
    expect(resolveEdgeHandles('JSONInput', 'ArticleMetadata')).toEqual({
      sourceHandle: 'text',
      targetHandle: 'text',
    })
  })

  it('disables Embed Text when no embedding models are enabled for the project', () => {
    const withoutModels = getCompatibleNextNodes('TextInput', ['TextInput'], {
      projectModelCapabilities: { embedding: false },
    })
    const embed = withoutModels.disabled.find((e) => e.type === 'EmbedText')
    expect(embed).toBeDefined()
    expect(embed?.reason).toMatch(/embedding model/i)

    const withModels = getCompatibleNextNodes('TextInput', ['TextInput'], {
      projectModelCapabilities: { embedding: true },
    })
    expect(withModels.enabled.map((e) => e.type)).toContain('EmbedText')
  })

  it('disables chaining the same step type directly after itself', () => {
    const result = getCompatibleNextNodes('OrganizationExtract', [
      'TextInput',
      'OrganizationExtract',
    ])
    expect(result.enabled.map((e) => e.type)).not.toContain('OrganizationExtract')

    const org = result.disabled.find((e) => e.type === 'OrganizationExtract')
    expect(org?.reason).toMatch(/cannot follow another Organization Extract step/i)
  })

  it('allows serial Article Metadata dimension chains', () => {
    const result = getCompatibleNextNodes('ArticleMetadata', ['TextInput', 'ArticleMetadata'], {
      projectModelCapabilities: { generative: true },
    })
    expect(result.enabled.map((e) => e.type)).toContain('ArticleMetadata')
  })

  it('enables Custom Extract from Text Input when generative models are available', () => {
    const result = getCompatibleNextNodes('TextInput', ['TextInput'], {
      projectModelCapabilities: { generative: true },
    })
    expect(result.enabled.map((e) => e.type)).toContain('CustomExtract')
    expect(resolveEdgeHandles('TextInput', 'CustomExtract')).toEqual({
      sourceHandle: 'text',
      targetHandle: 'text',
    })
  })

  it('allows serial Custom Extract record-type chains', () => {
    const result = getCompatibleNextNodes('CustomExtract', ['TextInput', 'CustomExtract'], {
      projectModelCapabilities: { generative: true },
    })
    expect(result.enabled.map((e) => e.type)).toContain('CustomExtract')
  })

  it('disables Article Metadata when no generative models are enabled for the project', () => {
    const withoutModels = getCompatibleNextNodes('TextInput', ['TextInput'], {
      projectModelCapabilities: { generative: false },
    })
    const metadata = withoutModels.disabled.find((e) => e.type === 'ArticleMetadata')
    expect(metadata).toBeDefined()
    expect(metadata?.reason).toMatch(/generative model/i)

    const withModels = getCompatibleNextNodes('TextInput', ['TextInput'], {
      projectModelCapabilities: { generative: true },
    })
    expect(withModels.enabled.map((e) => e.type)).toContain('ArticleMetadata')
  })

  it('enables Document Chunker from an input bookend when none exists yet', () => {
    const result = getCompatibleNextNodes('TextInput', ['TextInput'], {
      existingNodeTypes: ['TextInput', 'Output'],
    })
    expect(result.enabled.map((e) => e.type)).toContain('DocumentChunker')
  })

  it('disables Document Chunker after a middle step', () => {
    const result = getCompatibleNextNodes('PlaceExtract', ['TextInput', 'PlaceExtract'], {
      existingNodeTypes: ['TextInput', 'PlaceExtract', 'Output'],
    })
    expect(result.enabled.map((e) => e.type)).not.toContain('DocumentChunker')
    const chunker = result.disabled.find((e) => e.type === 'DocumentChunker')
    expect(chunker?.reason).toMatch(/directly after the content source/i)
  })

  it('disables Document Chunker when one already exists in the graph', () => {
    const result = getCompatibleNextNodes('TextInput', ['TextInput'], {
      existingNodeTypes: ['TextInput', 'DocumentChunker', 'Output'],
    })
    expect(result.enabled.map((e) => e.type)).not.toContain('DocumentChunker')
    const chunker = result.disabled.find((e) => e.type === 'DocumentChunker')
    expect(chunker?.reason).toMatch(/already has a Document Chunker/i)
  })
})

describe('getCompatibleInsertNodes', () => {
  it('enables Place Extract between Text Input and Geocode', () => {
    const result = getCompatibleInsertNodes('TextInput', 'GeocodeAgent', ['TextInput'])
    expect(result.enabled.map((e) => e.type)).toContain('PlaceExtract')
  })

  it('keeps invalid insert candidates disabled with a reason', () => {
    const result = getCompatibleInsertNodes('TextInput', 'GeocodeAgent', ['TextInput'])
    const geocode = result.disabled.find((e) => e.type === 'GeocodeAgent')
    expect(geocode?.reason).toMatch(/extracted places/i)
  })

  it('disables inserting the same step type adjacent to itself', () => {
    const result = getCompatibleInsertNodes(
      'OrganizationExtract',
      'DBOutput',
      ['TextInput', 'OrganizationExtract'],
    )
    expect(result.enabled.map((e) => e.type)).not.toContain('OrganizationExtract')

    const org = result.disabled.find((e) => e.type === 'OrganizationExtract')
    expect(org?.reason).toMatch(/cannot follow another Organization Extract step/i)
  })

  it('enables Gather before Backfield Output', () => {
    const result = getCompatibleInsertNodes('TextInput', 'DBOutput', ['TextInput'])
    expect(result.enabled.map((e) => e.type)).toContain('Gather')
  })

  it('enables Document Chunker between content source and a middle step', () => {
    const result = getCompatibleInsertNodes('TextInput', 'PlaceExtract', ['TextInput'], {
      existingNodeTypes: ['TextInput', 'PlaceExtract', 'Output'],
    })
    expect(result.enabled.map((e) => e.type)).toContain('DocumentChunker')
  })

  it('disables inserting Document Chunker after a middle step', () => {
    const result = getCompatibleInsertNodes(
      'PlaceExtract',
      'GeocodeAgent',
      ['TextInput', 'PlaceExtract'],
      { existingNodeTypes: ['TextInput', 'PlaceExtract', 'GeocodeAgent', 'Output'] },
    )
    expect(result.enabled.map((e) => e.type)).not.toContain('DocumentChunker')
    const chunker = result.disabled.find((e) => e.type === 'DocumentChunker')
    expect(chunker?.reason).toMatch(/directly after the content source/i)
  })
})

describe('resolveEdgeHandles', () => {
  it('maps Text Input to Place Extract on the text port', () => {
    expect(resolveEdgeHandles('TextInput', 'PlaceExtract')).toEqual({
      sourceHandle: 'text',
      targetHandle: 'text',
    })
  })

  it('maps Place Extract to JSON Output on locations → data', () => {
    expect(resolveEdgeHandles('PlaceExtract', 'Output')).toEqual({
      sourceHandle: 'locations',
      targetHandle: 'data',
    })
  })

  it('maps Text Input to Backfield Output on text → data', () => {
    expect(resolveEdgeHandles('TextInput', 'DBOutput')).toEqual({
      sourceHandle: 'text',
      targetHandle: 'data',
    })
  })

  it('maps Gather to Backfield Output on gathered → data', () => {
    expect(resolveEdgeHandles('Gather', 'DBOutput')).toEqual({
      sourceHandle: 'gathered',
      targetHandle: 'data',
    })
  })

  it('maps Gather to JSON Output on gathered → data', () => {
    expect(resolveEdgeHandles('Gather', 'Output')).toEqual({
      sourceHandle: 'gathered',
      targetHandle: 'data',
    })
  })

  it('maps any upstream node to Gather on data', () => {
    expect(resolveEdgeHandles('TextInput', 'Gather')).toEqual({
      sourceHandle: 'text',
      targetHandle: 'data',
    })
    expect(resolveEdgeHandles('PlaceExtract', 'Gather')).toEqual({
      sourceHandle: 'locations',
      targetHandle: 'data',
    })
  })

  it('maps JSON Input to Place and Person Extract on the text port', () => {
    expect(resolveEdgeHandles('JSONInput', 'PlaceExtract')).toEqual({
      sourceHandle: 'text',
      targetHandle: 'text',
    })
    expect(resolveEdgeHandles('JSONInput', 'PersonExtract')).toEqual({
      sourceHandle: 'text',
      targetHandle: 'text',
    })
    expect(resolveEdgeHandles('JSONInput', 'OrganizationExtract')).toEqual({
      sourceHandle: 'text',
      targetHandle: 'text',
    })
  })
})
