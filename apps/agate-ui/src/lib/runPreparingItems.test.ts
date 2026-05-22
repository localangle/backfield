import { describe, expect, it } from 'vitest'
import { isRunPreparingItems, PREPARING_ITEMS_SOURCE_LABEL } from './runPreparingItems'

describe('runPreparingItems', () => {
  it('detects placeholder rows before server item counts exist', () => {
    expect(
      isRunPreparingItems({ total_items: 0, items: [{ id: 1, synthetic: true }] }),
    ).toBe(true)
  })

  it('is false when the server reports real items', () => {
    expect(isRunPreparingItems({ total_items: 3, items: [{}, {}, {}] })).toBe(false)
  })

  it('is false when there are no rows to show', () => {
    expect(isRunPreparingItems({ total_items: 0, items: [] })).toBe(false)
    expect(isRunPreparingItems({ total_items: 0, items: undefined })).toBe(false)
  })

  it('exports preparing source label', () => {
    expect(PREPARING_ITEMS_SOURCE_LABEL).toBe('Preparing items ...')
  })
})
