import { describe, expect, it } from 'vitest'
import { isProcessedItemReviewLocked } from './processedItemReviewLock'

describe('isProcessedItemReviewLocked', () => {
  it('locks while a rerun request is in flight', () => {
    expect(isProcessedItemReviewLocked({ status: 'succeeded' }, true)).toBe(true)
  })

  it('locks while the item is pending or running', () => {
    expect(isProcessedItemReviewLocked({ status: 'pending' }, false)).toBe(true)
    expect(isProcessedItemReviewLocked({ status: 'running' }, false)).toBe(true)
  })

  it('unlocks when the item finished and no rerun is active', () => {
    expect(isProcessedItemReviewLocked({ status: 'succeeded' }, false)).toBe(false)
    expect(isProcessedItemReviewLocked({ status: 'failed' }, false)).toBe(false)
  })
})
