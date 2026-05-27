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

  it('splits place extract configuration across settings, models, and prompts', () => {
    expect(getNodePanelTabs('PlaceExtract')).toEqual(['settings', 'models', 'prompts'])
    expect(getNodePanelTabs('PlaceExtract', { hasRunOutput: true })).toEqual([
      'settings',
      'models',
      'prompts',
      'outputs',
    ])
  })

  it('shows outputs only for JSON output when a run exists', () => {
    expect(getNodePanelTabs('Output')).toEqual([])
    expect(getNodePanelTabs('Output', { hasRunOutput: true })).toEqual(['outputs'])
  })

  it('shows settings only for backfield output', () => {
    expect(getNodePanelTabs('DBOutput')).toEqual(['settings'])
  })
})
