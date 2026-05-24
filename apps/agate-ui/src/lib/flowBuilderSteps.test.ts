import { describe, expect, it } from 'vitest'
import { canContinueBookendNode, canNavigateToStep } from './flowBuilderSteps'

describe('canNavigateToStep', () => {
  it('allows only Input on a new flow', () => {
    const completed = new Set<'input' | 'output' | 'scaffold'>()
    expect(canNavigateToStep('input', completed)).toBe(true)
    expect(canNavigateToStep('output', completed)).toBe(false)
    expect(canNavigateToStep('scaffold', completed)).toBe(false)
  })

  it('allows Output after Input is completed', () => {
    const completed = new Set<'input' | 'output' | 'scaffold'>(['input'])
    expect(canNavigateToStep('input', completed)).toBe(true)
    expect(canNavigateToStep('output', completed)).toBe(true)
    expect(canNavigateToStep('scaffold', completed)).toBe(false)
  })

  it('allows Scaffold after Output is completed', () => {
    const completed = new Set<'input' | 'output' | 'scaffold'>(['input', 'output'])
    expect(canNavigateToStep('scaffold', completed)).toBe(true)
  })

  it('allows navigating back to completed steps', () => {
    const completed = new Set<'input' | 'output' | 'scaffold'>(['input', 'output'])
    expect(canNavigateToStep('input', completed)).toBe(true)
    expect(canNavigateToStep('output', completed)).toBe(true)
  })

  it('blocks Scaffold until Output is completed even when Input is done', () => {
    const completed = new Set<'input' | 'output' | 'scaffold'>(['input'])
    expect(canNavigateToStep('scaffold', completed)).toBe(false)
  })

  it('allows free navigation among all steps once Input and Output are complete', () => {
    const completed = new Set<'input' | 'output' | 'scaffold'>(['input', 'output', 'scaffold'])
    expect(canNavigateToStep('input', completed)).toBe(true)
    expect(canNavigateToStep('output', completed)).toBe(true)
    expect(canNavigateToStep('scaffold', completed)).toBe(true)
  })
})

describe('canContinueBookendNode', () => {
  it('requires S3 bucket name', () => {
    expect(canContinueBookendNode({ type: 'S3Input', data: { bucket: '' } })).toBe(false)
    expect(canContinueBookendNode({ type: 'S3Input', data: { bucket: 'my-bucket' } })).toBe(true)
  })

  it('requires JSON text field', () => {
    expect(canContinueBookendNode({ type: 'JSONInput', data: { text: '' } })).toBe(false)
    expect(canContinueBookendNode({ type: 'JSONInput', data: { text: 'hello' } })).toBe(true)
  })

  it('allows Text Input without sample text', () => {
    expect(canContinueBookendNode({ type: 'TextInput', data: { text: '' } })).toBe(true)
  })

  it('allows JSON Output without extra settings', () => {
    expect(canContinueBookendNode({ type: 'Output', data: {} })).toBe(true)
  })

  it('allows Stylebook Output with default params', () => {
    expect(
      canContinueBookendNode({
        type: 'DBOutput',
        data: { stylebook_id: null, canonicalization_mode: 'rules' },
      }),
    ).toBe(true)
  })
})
