import { describe, expect, it } from 'vitest'
import {
  RERUN_WARNING_TITLE,
  RUN_AGAIN_WARNING_TITLE,
  reconciliationPolicyFromGraph,
  runAgainWarningBody,
  rerunWarningBody,
  rerunWarningTitle,
} from './rerunWarning'

describe('rerunWarning', () => {
  it('uses run-again copy on the run detail page', () => {
    expect(RUN_AGAIN_WARNING_TITLE).toBe('Rerun all items?')
    expect(runAgainWarningBody({ flowName: 'Starter', policy: 'smart_merge' })).toBe(
      'This will use the current saved version of “Starter” with Smart Merge. It will update saved data from the flow while preserving changes made by editors.',
    )
  })

  it('uses singular copy for one item', () => {
    expect(RERUN_WARNING_TITLE).toBe('Rerun item?')
    expect(rerunWarningTitle(1)).toBe('Rerun item?')
    expect(rerunWarningBody(1, { flowName: 'Places', policy: 'smart_merge' })).toBe(
      'This will use the current saved version of “Places” with Smart Merge. Run review edits on this item will be cleared. It will update saved data from the flow while preserving changes made by editors.',
    )
  })

  it('uses plural copy for bulk rerun', () => {
    expect(rerunWarningTitle(3)).toBe('Rerun items?')
    expect(rerunWarningBody(3, { flowName: 'Places', policy: 'replace' })).toBe(
      'This will use the current saved version of “Places” with Replace. Run review edits on these 3 items will be cleared. It will replace existing saved data from the flow’s categories with this run’s results.',
    )
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
