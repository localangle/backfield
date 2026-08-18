import { describe, expect, it } from 'vitest'

import {
  RERUN_ORIGINAL_FLOW_LABEL,
  RERUN_WARNING_TITLE,
  RUN_AGAIN_WARNING_TITLE,
  RUN_UPDATED_FLOW_LABEL,
  promptFlowRerun,
  reconciliationPolicyFromGraph,
  runAgainWarningBody,
  rerunWarningBody,
  rerunWarningTitle,
  shouldOfferUpdatedFlow,
} from './rerunWarning'

describe('rerunWarning', () => {
  it('uses replay copy on the run detail page', () => {
    expect(RUN_AGAIN_WARNING_TITLE).toBe('Replay run?')
    expect(runAgainWarningBody({ flowName: 'Starter', policy: 'smart_merge' })).toBe(
      'This will replay using the flow settings from when this run started (“Starter”) with Smart Merge. It will update saved data from the flow while preserving changes made by editors.',
    )
  })

  it('uses singular copy for one item', () => {
    expect(RERUN_WARNING_TITLE).toBe('Rerun item?')
    expect(rerunWarningTitle(1)).toBe('Rerun item?')
    expect(rerunWarningBody(1, { flowName: 'Places', policy: 'smart_merge' })).toBe(
      'This will replay using the flow settings from when this run started (“Places”) with Smart Merge. Run review edits on this item will be cleared. It will update saved data from the flow while preserving changes made by editors.',
    )
  })

  it('uses plural copy for bulk rerun', () => {
    expect(rerunWarningTitle(3)).toBe('Rerun items?')
    expect(rerunWarningBody(3, { flowName: 'Places', policy: 'replace' })).toBe(
      'This will replay using the flow settings from when this run started (“Places”) with Replace. Run review edits on these 3 items will be cleared. It will replace existing saved data from the flow’s categories with this run’s results.',
    )
  })

  it('mentions the current saved flow when both actions are offered', () => {
    expect(
      rerunWarningBody(1, {
        flowName: 'Places',
        policy: 'smart_merge',
        offerUpdatedFlow: true,
      }),
    ).toContain('Run updated flow uses the current saved flow.')
    expect(
      runAgainWarningBody({
        flowName: 'Starter',
        policy: 'smart_merge',
        offerUpdatedFlow: true,
      }),
    ).toContain('Run updated flow uses the current saved flow.')
  })

  it('offers the updated-flow action only when the saved flow changed', () => {
    expect(shouldOfferUpdatedFlow(true)).toBe(true)
    expect(shouldOfferUpdatedFlow(false)).toBe(false)
    expect(shouldOfferUpdatedFlow(null)).toBe(false)
  })

  it('prompts original vs updated flow only when the saved flow changed', async () => {
    const showConfirm = async () => true
    const showConfirmChoice = async () => 'secondary' as const
    await expect(
      promptFlowRerun({
        flowChanged: false,
        title: RERUN_WARNING_TITLE,
        unchangedConfirmLabel: 'Rerun',
        description: 'body',
        originalPolicy: 'smart_merge',
        updatedPolicy: 'replace',
        showConfirm,
        showConfirmChoice,
      }),
    ).resolves.toBe('original')
    await expect(
      promptFlowRerun({
        flowChanged: true,
        title: RERUN_WARNING_TITLE,
        unchangedConfirmLabel: 'Rerun',
        description: 'body',
        originalPolicy: 'smart_merge',
        updatedPolicy: 'replace',
        showConfirm,
        showConfirmChoice,
      }),
    ).resolves.toBe('updated')
    expect(RERUN_ORIGINAL_FLOW_LABEL).toBe('Rerun original flow')
    expect(RUN_UPDATED_FLOW_LABEL).toBe('Run updated flow')
  })

  it('reads the Backfield Output policy from graph params', () => {
    expect(
      reconciliationPolicyFromGraph({
        spec: {
          nodes: [
            { type: 'TextInput', params: {} },
            { type: 'DBOutput', params: { reconciliation_policy: 'add_only' } },
          ],
        },
      }),
    ).toBe('add_only')
  })
})
