import { describe, expect, it } from 'vitest'
import {
  RERUN_WARNING_TITLE,
  RUN_AGAIN_WARNING_BODY,
  RUN_AGAIN_WARNING_TITLE,
  rerunWarningBody,
  rerunWarningTitle,
} from './rerunWarning'

describe('rerunWarning', () => {
  it('uses run-again copy on the run detail page', () => {
    expect(RUN_AGAIN_WARNING_TITLE).toBe('Rerun all items?')
    expect(RUN_AGAIN_WARNING_BODY).toBe(
      'Re-running will replace all manual edits that have been made to all selected items.',
    )
  })

  it('uses singular copy for one item', () => {
    expect(RERUN_WARNING_TITLE).toBe('Rerun item?')
    expect(rerunWarningTitle(1)).toBe('Rerun item?')
    expect(rerunWarningBody(1)).toBe(
      'Re-running will replace all manual edits that have been made to this item.',
    )
  })

  it('uses plural copy for bulk rerun', () => {
    expect(rerunWarningTitle(3)).toBe('Rerun items?')
    expect(rerunWarningBody(3)).toBe(
      'Re-running will replace all manual edits that have been made to these 3 items.',
    )
  })
})
