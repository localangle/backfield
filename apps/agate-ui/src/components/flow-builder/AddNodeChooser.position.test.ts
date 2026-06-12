import { describe, expect, it } from 'vitest'
import { positionAddNodeChooserMenu } from './AddNodeChooser'

const VIEWPORT = { width: 1200, height: 800 }
const MENU_MAX_HEIGHT = 360
const MENU_GAP = 8

describe('positionAddNodeChooserMenu', () => {
  it('opens to the right of the anchor when there is room', () => {
    const anchor = { top: 100, right: 400, bottom: 140, left: 320 }
    const { left } = positionAddNodeChooserMenu(anchor, VIEWPORT)
    expect(left).toBe(408)
  })

  it('opens to the left of the anchor when the right edge is too close', () => {
    const anchor = { top: 100, right: 900, bottom: 140, left: 860 }
    const { left } = positionAddNodeChooserMenu(anchor, VIEWPORT)
    expect(left).toBe(512)
  })

  it('aligns the menu top with the anchor when there is room', () => {
    const anchor = { top: 100, right: 400, bottom: 140, left: 320 }
    const { top } = positionAddNodeChooserMenu(anchor, VIEWPORT)
    expect(top).toBe(100)
  })

  it('keeps short menus adjacent instead of reserving full max height', () => {
    const anchor = { top: 520, right: 400, bottom: 560, left: 320 }
    const { top } = positionAddNodeChooserMenu(anchor, VIEWPORT, 120)
    expect(top).toBe(520)
  })

  it('opens above the anchor when a tall menu would overflow the viewport', () => {
    const anchor = { top: 520, right: 400, bottom: 560, left: 320 }
    const { top } = positionAddNodeChooserMenu(anchor, VIEWPORT, MENU_MAX_HEIGHT)
    expect(top).toBe(152)
    expect(top + MENU_MAX_HEIGHT).toBeLessThanOrEqual(anchor.top - MENU_GAP)
  })

  it('clamps into the viewport when neither side fits the full menu height', () => {
    const anchor = { top: 380, right: 400, bottom: 420, left: 320 }
    const { top } = positionAddNodeChooserMenu(anchor, VIEWPORT, MENU_MAX_HEIGHT)
    expect(top).toBeGreaterThanOrEqual(MENU_GAP)
    expect(top + MENU_MAX_HEIGHT).toBeLessThanOrEqual(VIEWPORT.height - MENU_GAP)
  })

  it('keeps the menu on-screen when the anchor sits on the bottom edge', () => {
    const anchor = { top: 760, right: 400, bottom: 792, left: 320 }
    const { top } = positionAddNodeChooserMenu(anchor, VIEWPORT, MENU_MAX_HEIGHT)
    expect(top).toBe(392)
    expect(top).toBeGreaterThanOrEqual(MENU_GAP)
    expect(top + MENU_MAX_HEIGHT).toBeLessThanOrEqual(VIEWPORT.height - MENU_GAP)
  })
})
