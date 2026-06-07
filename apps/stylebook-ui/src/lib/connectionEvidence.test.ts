import { describe, expect, it } from 'vitest'
import { formatConnectionEvidence, hasConnectionEvidence } from './connectionEvidence'

describe('connectionEvidence helpers', () => {
  it('returns null for manual connections without evidence', () => {
    expect(hasConnectionEvidence(null)).toBe(false)
    expect(formatConnectionEvidence(undefined)).toBeNull()
  })

  it('formats automatic connection evidence for display', () => {
    const view = formatConnectionEvidence({
      source: 'dboutput_auto_connections',
      confidence: 0.94,
      quote: 'Mayor Jane Smith works for Chicago City Hall.',
      reason: 'The story states an employment relationship.',
    })
    expect(view).not.toBeNull()
    expect(view?.confidenceLabel).toBe('94% confidence')
    expect(view?.quote).toContain('Jane Smith')
    expect(view?.reason).toContain('employment')
    expect(view?.sourceLabel).toContain('automatically')
  })
})
