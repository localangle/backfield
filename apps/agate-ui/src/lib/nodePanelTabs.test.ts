import { describe, expect, it } from 'vitest'

import { getNodePanelTabs } from './nodePanelTabs'

describe('getNodePanelTabs', () => {
  it('shows settings only for text input without a run', () => {
    expect(getNodePanelTabs('TextInput')).toEqual(['settings'])
  })

  it('shows settings and info for JSON input without a run', () => {
    expect(getNodePanelTabs('JSONInput')).toEqual(['settings', 'info'])
    expect(getNodePanelTabs('JSONInput', { hasRunOutput: true })).toEqual([
      'settings',
      'info',
      'outputs',
    ])
  })

  it('adds outputs when a run exists for inputs', () => {
    expect(getNodePanelTabs('S3Input', { hasRunOutput: true })).toEqual(['settings', 'outputs'])
  })

  it('splits place extract configuration across settings, prompt, output, and info', () => {
    expect(getNodePanelTabs('PlaceExtract')).toEqual(['settings', 'prompts', 'outputs', 'info'])
    expect(getNodePanelTabs('PlaceExtract', { hasRunOutput: true })).toEqual([
      'settings',
      'prompts',
      'outputs',
      'info',
    ])
  })

  it('shows settings and models for geocode agent', () => {
    expect(getNodePanelTabs('GeocodeAgent')).toEqual(['settings', 'models'])
    expect(getNodePanelTabs('GeocodeAgent', { hasRunOutput: true })).toEqual(['settings', 'models'])
  })

  it('shows outputs only for JSON output when a run exists', () => {
    expect(getNodePanelTabs('Output')).toEqual([])
    expect(getNodePanelTabs('Output', { hasRunOutput: true })).toEqual(['outputs'])
  })

  it('shows settings and stylebook for backfield output', () => {
    expect(getNodePanelTabs('DBOutput')).toEqual(['settings', 'stylebook'])
  })

  it('shows settings and info for embed text', () => {
    expect(getNodePanelTabs('EmbedText')).toEqual(['settings', 'info'])
    expect(getNodePanelTabs('EmbedText', { hasRunOutput: true })).toEqual(['settings', 'info'])
  })

  it('shows settings and info for embed images', () => {
    expect(getNodePanelTabs('EmbedImages')).toEqual(['settings', 'info'])
    expect(getNodePanelTabs('EmbedImages', { hasRunOutput: true })).toEqual(['settings', 'info'])
  })

  it('shows settings, info, and outputs for gather when a run exists', () => {
    expect(getNodePanelTabs('Gather')).toEqual(['settings', 'info'])
    expect(getNodePanelTabs('Gather', { hasRunOutput: true })).toEqual([
      'settings',
      'info',
      'outputs',
    ])
  })

  it('splits article metadata configuration across settings, prompt, output, and info', () => {
    expect(getNodePanelTabs('ArticleMetadata')).toEqual(['settings', 'prompts', 'outputs', 'info'])
  })

  it('splits custom extract configuration across settings, prompt, output, and info', () => {
    expect(getNodePanelTabs('CustomExtract')).toEqual(['settings', 'prompts', 'outputs', 'info'])
  })
})
