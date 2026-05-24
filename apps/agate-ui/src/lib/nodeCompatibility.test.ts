import { describe, expect, it } from 'vitest'
import { getCompatibleNextNodes, shouldShowChooserSearch } from './nodeCompatibility'

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
})

describe('chooser search threshold', () => {
  it('defers search until the scaffold catalog exceeds eight node types', () => {
    expect(shouldShowChooserSearch(8)).toBe(false)
    expect(shouldShowChooserSearch(9)).toBe(true)
  })
})
