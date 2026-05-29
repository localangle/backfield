import { describe, expect, it } from 'vitest'
import { jsonInputInvalidNodeData } from '@/lib/jsonInputValidation'
import {
  canContinueBookendNode,
  canNavigateToStep,
  canSavePanelChanges,
  completedStepsForEdit,
  getInitialEditStep,
  isPanelGateActive,
} from './flowBuilderSteps'

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
    expect(canContinueBookendNode({ type: 'S3Input', data: { bucket: 's3://my-bucket' } })).toBe(true)
  })

  it('requires JSON object with string text field (may be empty)', () => {
    expect(canContinueBookendNode({ type: 'JSONInput', data: { text: '' } })).toBe(true)
    expect(canContinueBookendNode({ type: 'JSONInput', data: { text: 'hello' } })).toBe(true)
    expect(canContinueBookendNode({ type: 'JSONInput', data: { headline: 'Title' } })).toBe(false)
    expect(canContinueBookendNode({ type: 'JSONInput', data: { text: 1 } })).toBe(false)
    expect(canContinueBookendNode({ type: 'JSONInput', data: jsonInputInvalidNodeData() })).toBe(
      false,
    )
  })

  it('allows Text Input without sample text', () => {
    expect(canContinueBookendNode({ type: 'TextInput', data: { text: '' } })).toBe(true)
  })

  it('allows JSON Output without extra settings', () => {
    expect(canContinueBookendNode({ type: 'Output', data: {} })).toBe(true)
  })

  it('allows Backfield Output with default params', () => {
    expect(
      canContinueBookendNode({
        type: 'DBOutput',
        data: {
          stylebook_matching_enabled: true,
          stylebook_id: null,
          canonicalization_mode: 'ai_assisted',
        },
      }),
    ).toBe(true)
  })
})

describe('isPanelGateActive', () => {
  it('keeps Continue/Cancel on wizard bookend steps when revisiting', () => {
    expect(
      isPanelGateActive({
        readOnly: false,
        configureGateActive: false,
        activeStep: 'input',
        isBookendSelected: true,
      }),
    ).toBe(true)
    expect(
      isPanelGateActive({
        readOnly: false,
        configureGateActive: false,
        activeStep: 'output',
        isBookendSelected: true,
      }),
    ).toBe(true)
  })

  it('uses Save on scaffold when the configure gate is cleared', () => {
    expect(
      isPanelGateActive({
        readOnly: false,
        configureGateActive: false,
        activeStep: 'scaffold',
        isBookendSelected: true,
      }),
    ).toBe(false)
  })
})

describe('canSavePanelChanges', () => {
  it('blocks server save on wizard bookend steps', () => {
    expect(
      canSavePanelChanges({
        activeStep: 'input',
        inputNode: {},
        outputNode: null,
        hasChanges: true,
      }),
    ).toBe(false)
  })

  it('allows server save on scaffold when both bookends exist and the panel is dirty', () => {
    expect(
      canSavePanelChanges({
        activeStep: 'scaffold',
        inputNode: {},
        outputNode: {},
        hasChanges: true,
      }),
    ).toBe(true)
  })
})

describe('edit mode defaults', () => {
  it('opens existing flows on the scaffold step', () => {
    expect(getInitialEditStep()).toBe('scaffold')
  })

  it('marks input and output complete when editing', () => {
    expect(completedStepsForEdit()).toEqual(new Set(['input', 'output']))
  })
})
