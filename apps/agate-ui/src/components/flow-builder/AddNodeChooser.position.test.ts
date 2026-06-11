import { describe, expect, it } from 'vitest'
import { positionAddNodeChooserMenu } from './AddNodeChooser'

const VIEWPORT = { width: 1200, height: 800 }
const MENU_MAX_HEIGHT = 360
const MENU_GAP = 8

describe('positionAddNodeChooserMenu', () => {
  it('opens below the anchor when there is room for the full menu', () => {
    const anchor = { top: 100, right: 400, bottom: 140, left: 320 }
    const { top } = positionAddNodeChooserMenu(anchor, VIEWPORT)
    expect(top).toBe(148)
  })

  it('opens above the anchor when the bottom edge is too close', () => {
    const anchor = { top: 520, right: 400, bottom: 560, left: 320 }
    const { top } = positionAddNodeChooserMenu(anchor, VIEWPORT)
    expect(top).toBe(152)
    expect(top + MENU_MAX_HEIGHT).toBeLessThanOrEqual(VIEWPORT.height - MENU_GAP)
  })

  it('clamps into the viewport when neither side fits the full menu height', () => {
    const anchor = { top: 380, right: 400, bottom: 420, left: 320 }
    const { top } = positionAddNodeChooserMenu(anchor, VIEWPORT)
    expect(top).toBeGreaterThanOrEqual(MENU_GAP)
    expect(top + MENU_MAX_HEIGHT).toBeLessThanOrEqual(VIEWPORT.height - MENU_GAP)
  })

  it('keeps the menu on-screen when the anchor sits on the bottom edge', () => {
    const anchor = { top: 760, right: 400, bottom: 792, left: 320 }
    const { top } = positionAddNodeChooserMenu(anchor, VIEWPORT)
    expect(top).toBe(392)
    expect(top).toBeGreaterThanOrEqual(MENU_GAP)
    expect(top + MENU_MAX_HEIGHT).toBeLessThanOrEqual(VIEWPORT.height - MENU_GAP)
  })
})
