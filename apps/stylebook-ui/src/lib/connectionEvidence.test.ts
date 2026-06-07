import { describe, expect, it } from 'vitest'
import {
  formatConnectionEvidence,
  hasConnectionEvidence,
  shouldShowEvidenceReason,
} from './connectionEvidence'

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
    expect(view?.confidencePercent).toBe(94)
    expect(view?.quote).toContain('Jane Smith')
    expect(view?.showReason).toBe(true)
  })

  it('hides boilerplate reasons that repeat the relationship nature', () => {
    expect(
      shouldShowEvidenceReason(
        'Grant Achatz, owner and head chef of Alinea, disagreed.',
        'Explicit leadership role (owner/head chef) of Alinea evidenced in snippet; supports leads relationship.',
      ),
    ).toBe(false)
  })
})
