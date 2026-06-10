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
