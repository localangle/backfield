import { describe, expect, it } from 'vitest'
import {
  RERUN_GEOGRAPHY_WARNING_TITLE,
  rerunGeographyWarningBody,
} from './rerunGeographyWarning'

describe('rerunGeographyWarning', () => {
  it('uses singular copy for one item', () => {
    expect(RERUN_GEOGRAPHY_WARNING_TITLE).toBe('Replace saved places?')
    expect(rerunGeographyWarningBody(1)).toContain('this story')
    expect(rerunGeographyWarningBody(1)).not.toContain('these')
  })

  it('uses plural copy for bulk rerun', () => {
    expect(rerunGeographyWarningBody(3)).toContain('these 3 stories')
  })
})
